"""Test di integrazione con un vero PostgREST + PostgreSQL (come Supabase).

Si esegue solo se sono impostate:
  POSTGREST_URL   es. http://localhost:3000
  POSTGREST_JWT_SECRET
Il database deve contenere schema.sql + seed.sql con owner_email = io@example.org.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import httpx
import pytest

from giornale.config import Config
from giornale.llm import LLM
from giornale.run import run_pipeline
from giornale.store import SupabaseStore

from .test_pipeline import NOW, FakeProvider, FakeReader, _fetcher, _script

URL = os.getenv("POSTGREST_URL")
SECRET = os.getenv("POSTGREST_JWT_SECRET")
pytestmark = pytest.mark.skipif(not (URL and SECRET), reason="PostgREST di prova non configurato")


def jwt(claims: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    head = enc({"alg": "HS256", "typ": "JWT"})
    body = enc({**claims, "exp": int(time.time()) + 3600})
    sig = hmac.new(SECRET.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"


def make_store() -> SupabaseStore:
    store = SupabaseStore("http://unused", jwt({"role": "service_role"}))
    store.client.base_url = URL
    return store


def _reset(store: SupabaseStore):
    """Svuota le tabelle dei contenuti (database di prova)."""
    for table in ("glossary_story_links", "user_story_state", "story_sources", "stories", "editions", "runs"):
        col = "story_id" if table in ("glossary_story_links", "user_story_state") else "id"
        store._req("DELETE", f"/{table}", params={col: "not.is.null"})
    store._req("PATCH", "/sources", params={"id": "not.is.null"}, json={"last_status": None, "consecutive_failures": 0})


def test_pipeline_su_postgrest():
    store = make_store()
    _reset(store)
    # la configurazione reale contiene le fonti del seed: il fetcher simulato fornisce voci per ISTAT e ANSA – Economia
    llm_factory = lambda n: LLM([FakeProvider("fake-flash", _script())], max_requests=n, min_interval=0,
                                sleep=lambda s: None)
    out = run_pipeline(store, Config(force=True, trigger="test"), fetcher=_fetcher(store), reader=FakeReader(),
                       llm_factory=llm_factory, now_utc=NOW)
    assert out.status in ("success", "partial"), out.errors
    assert len(out.published) == 1

    owner = httpx.Client(base_url=URL, headers={"Authorization": f"Bearer {jwt({'role': 'authenticated', 'email': 'io@example.org'})}"})
    stories = owner.get("/stories", params={"select": "title,verification_level,is_must_read,story_sources(ref,url)"}).json()
    assert len(stories) == 1 and stories[0]["is_must_read"] is True
    assert {s["ref"] for s in stories[0]["story_sources"]} == {"S1", "S2"}
    links = owner.get("/glossary_story_links", params={"select": "glossary(slug)"}).json()
    assert {l["glossary"]["slug"] for l in links} == {"inflazione"}
    runs = owner.get("/runs", params={"select": "status,stories_published,requests_used"}).json()
    assert runs[-1]["stories_published"] == 1 and runs[-1]["requests_used"] > 0
    srcs = owner.get("/sources", params={"select": "name,last_status", "last_status": "not.is.null"}).json()
    assert len(srcs) == 17

    intruder = httpx.Client(base_url=URL, headers={"Authorization": f"Bearer {jwt({'role': 'authenticated', 'email': 'x@y.z'})}"})
    assert intruder.get("/stories").json() == []
    # le notizie già usate non vengono riproposte nella stessa giornata
    assert store.recent_source_urls(4) >= {"https://www.istat.it/x", "https://www.ansa.it/y"}


def test_sostituzione_scheda_su_postgrest():
    store = make_store()
    _reset(store)
    ed = store.get_or_create_edition(__import__("datetime").date(2026, 10, 10))
    base = {"edition_id": ed["id"], "edition_date": "2026-10-10", "category_slug": "banche", "title": "Vecchio titolo",
            "summary": "s", "verification_level": "fonte_singola"}
    sid = store.insert_story(base, [{"ref": "S1", "source_name": "A", "title": "a", "url": "https://a.it/1"}])
    store.replace_story(sid, {**base, "title": "Nuovo titolo", "verification_notes": ["Scheda aggiornata"]},
                        [{"ref": "S1", "source_name": "B", "title": "b", "url": "https://b.it/2"},
                         {"ref": "S2", "source_name": "C", "title": "c", "url": "https://c.it/3"}])
    rows = store._get("stories", {"select": "id,title,story_sources(url)"})
    assert len(rows) == 1 and rows[0]["title"] == "Nuovo titolo"
    assert sorted(x["url"] for x in rows[0]["story_sources"]) == ["https://b.it/2", "https://c.it/3"]
