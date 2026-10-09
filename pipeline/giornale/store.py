"""Accesso al database.

SupabaseStore parla con Supabase (PostgREST) usando la chiave di servizio.
MemoryStore tiene tutto in memoria: serve per i test e per le prove locali.
"""
from __future__ import annotations

import copy
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StoreError(RuntimeError):
    pass


class BaseStore:
    # --- impostazioni e configurazione ---
    def get_settings(self) -> dict: ...
    def list_categories(self) -> list[dict]: ...
    def list_sources(self) -> list[dict]: ...
    def update_source(self, source_id: str, fields: dict) -> None: ...
    # --- esecuzioni ---
    def runs_for_slot(self, slot: str) -> list[dict]: ...
    def create_run(self, fields: dict) -> dict: ...
    def update_run(self, run_id: str, fields: dict) -> None: ...
    def last_good_run(self) -> dict | None: ...
    # --- edizioni e notizie ---
    def get_or_create_edition(self, edition_date: date) -> dict: ...
    def update_edition(self, edition_id: str, fields: dict) -> None: ...
    def recent_stories(self, days: int) -> list[dict]: ...
    def recent_source_urls(self, days: int) -> set[str]: ...
    def stories_for_edition(self, edition_id: str) -> list[dict]: ...
    def insert_story(self, story: dict, sources: list[dict]) -> str: ...
    def update_story(self, story_id: str, fields: dict) -> None: ...
    # --- glossario ---
    def glossary_all(self) -> list[dict]: ...
    def insert_glossary(self, entry: dict) -> str: ...
    def link_glossary(self, links: list[tuple[str, str]]) -> None: ...


class SupabaseStore(BaseStore):
    def __init__(self, url: str, key: str, timeout: float = 30.0):
        headers = {"apikey": key, "Content-Type": "application/json"}
        if key.startswith("eyJ"):  # chiave service_role in formato JWT (legacy)
            headers["Authorization"] = f"Bearer {key}"
        self.client = httpx.Client(base_url=f"{url}/rest/v1", headers=headers, timeout=timeout)

    # -- utilità --
    def _req(self, method: str, path: str, **kw) -> Any:
        r = self.client.request(method, path, **kw)
        if r.status_code >= 400:
            raise StoreError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
        if not r.content:
            return None
        return r.json()

    def _get(self, table: str, params: dict) -> list[dict]:
        return self._req("GET", f"/{table}", params=params) or []

    def _insert(self, table: str, rows: list[dict] | dict) -> list[dict]:
        return self._req("POST", f"/{table}", json=rows, headers={"Prefer": "return=representation"}) or []

    def _patch(self, table: str, filters: dict, fields: dict) -> None:
        self._req("PATCH", f"/{table}", params=filters, json=fields, headers={"Prefer": "return=minimal"})

    # -- implementazione --
    def get_settings(self) -> dict:
        rows = self._get("settings", {"id": "eq.1", "select": "*"})
        if not rows:
            raise StoreError("Tabella settings vuota: eseguire supabase/seed.sql")
        return rows[0]

    def list_categories(self) -> list[dict]:
        return self._get("categories", {"select": "*", "order": "priority.desc,name.asc"})

    def list_sources(self) -> list[dict]:
        return self._get("sources", {"select": "*", "order": "name.asc"})

    def update_source(self, source_id: str, fields: dict) -> None:
        self._patch("sources", {"id": f"eq.{source_id}"}, fields)

    def runs_for_slot(self, slot: str) -> list[dict]:
        return self._get("runs", {"slot": f"eq.{slot}", "select": "*"})

    def create_run(self, fields: dict) -> dict:
        return self._insert("runs", fields)[0]

    def update_run(self, run_id: str, fields: dict) -> None:
        self._patch("runs", {"id": f"eq.{run_id}"}, fields)

    def last_good_run(self) -> dict | None:
        rows = self._get("runs", {"status": "in.(success,partial)", "select": "*",
                                  "order": "started_at.desc", "limit": "1"})
        return rows[0] if rows else None

    def get_or_create_edition(self, edition_date: date) -> dict:
        rows = self._get("editions", {"edition_date": f"eq.{edition_date.isoformat()}", "select": "*"})
        if rows:
            return rows[0]
        return self._insert("editions", {"edition_date": edition_date.isoformat()})[0]

    def update_edition(self, edition_id: str, fields: dict) -> None:
        self._patch("editions", {"id": f"eq.{edition_id}"}, fields)

    def recent_stories(self, days: int) -> list[dict]:
        since = (date.today() - timedelta(days=days)).isoformat()
        return self._get("stories", {
            "edition_date": f"gte.{since}",
            "select": "id,title,summary,context,thread_id,edition_date,category_slug,verification_level",
            "order": "created_at.desc", "limit": "300"})

    def recent_source_urls(self, days: int) -> set[str]:
        since = (date.today() - timedelta(days=days)).isoformat()
        rows = self._get("story_sources", {
            "select": "url,stories!inner(edition_date)", "stories.edition_date": f"gte.{since}", "limit": "2000"})
        return {r["url"] for r in rows}

    def stories_for_edition(self, edition_id: str) -> list[dict]:
        return self._get("stories", {"edition_id": f"eq.{edition_id}", "select": "*"})

    def insert_story(self, story: dict, sources: list[dict]) -> str:
        row = self._insert("stories", story)[0]
        if sources:
            self._insert("story_sources", [{**s, "story_id": row["id"]} for s in sources])
        return row["id"]

    def update_story(self, story_id: str, fields: dict) -> None:
        self._patch("stories", {"id": f"eq.{story_id}"}, fields)

    def glossary_all(self) -> list[dict]:
        return self._get("glossary", {"select": "id,slug,term,aliases"})

    def insert_glossary(self, entry: dict) -> str:
        rows = self._req("POST", "/glossary", params={"on_conflict": "slug"}, json=entry,
                         headers={"Prefer": "return=representation,resolution=ignore-duplicates"}) or []
        if rows:
            return rows[0]["id"]
        existing = self._get("glossary", {"slug": f"eq.{entry['slug']}", "select": "id"})
        return existing[0]["id"]

    def link_glossary(self, links: list[tuple[str, str]]) -> None:
        if not links:
            return
        self._req("POST", "/glossary_story_links", params={"on_conflict": "glossary_id,story_id"},
                  json=[{"glossary_id": g, "story_id": s} for g, s in links],
                  headers={"Prefer": "return=minimal,resolution=ignore-duplicates"})


class MemoryStore(BaseStore):
    """Database in memoria con lo stesso comportamento minimo di SupabaseStore."""

    def __init__(self, settings: dict, categories: list[dict], sources: list[dict], glossary: list[dict] | None = None):
        self.settings = {"id": 1, "update_hours": [7], "timezone": "Europe/Rome", "excluded_topics": [],
                         "max_must_read": 5, "max_requests_per_run": 60, **settings}
        self.categories = [{"id": str(uuid.uuid4()), "enabled": True, "show_on_home": True, "is_custom": False,
                            **c} for c in categories]
        self.sources = [{"id": str(uuid.uuid4()), "enabled": True, "preferred": False, "consecutive_failures": 0,
                         "exclude_title_regex": None, **s} for s in sources]
        self.runs: list[dict] = []
        self.editions: list[dict] = []
        self.stories: list[dict] = []
        self.story_sources: list[dict] = []
        self.glossary = [{"id": str(uuid.uuid4()), **g} for g in (glossary or [])]
        self.glossary_links: set[tuple[str, str]] = set()

    def get_settings(self): return copy.deepcopy(self.settings)
    def list_categories(self): return copy.deepcopy(sorted(self.categories, key=lambda c: (-c["priority"], c["name"])))
    def list_sources(self): return copy.deepcopy(self.sources)

    def update_source(self, source_id, fields):
        for s in self.sources:
            if s["id"] == source_id:
                s.update(fields)

    def runs_for_slot(self, slot): return [r for r in self.runs if r.get("slot") == slot]

    def create_run(self, fields):
        run = {"id": str(uuid.uuid4()), "started_at": _now(), "status": "running", **fields}
        self.runs.append(run)
        return copy.deepcopy(run)

    def update_run(self, run_id, fields):
        for r in self.runs:
            if r["id"] == run_id:
                r.update(fields)

    def last_good_run(self):
        good = [r for r in self.runs if r["status"] in ("success", "partial")]
        return copy.deepcopy(good[-1]) if good else None

    def get_or_create_edition(self, edition_date):
        for e in self.editions:
            if e["edition_date"] == edition_date.isoformat():
                return copy.deepcopy(e)
        e = {"id": str(uuid.uuid4()), "edition_date": edition_date.isoformat(), "published_at": _now(),
             "updated_at": _now(), "notes": {}}
        self.editions.append(e)
        return copy.deepcopy(e)

    def update_edition(self, edition_id, fields):
        for e in self.editions:
            if e["id"] == edition_id:
                e.update(fields)

    def recent_stories(self, days):
        since = (date.today() - timedelta(days=days)).isoformat()
        return copy.deepcopy([s for s in self.stories if s["edition_date"] >= since])

    def recent_source_urls(self, days):
        ids = {s["id"] for s in self.recent_stories(days)}
        return {ss["url"] for ss in self.story_sources if ss["story_id"] in ids}

    def stories_for_edition(self, edition_id):
        return copy.deepcopy([s for s in self.stories if s["edition_id"] == edition_id])

    def insert_story(self, story, sources):
        sid = str(uuid.uuid4())
        self.stories.append({"id": sid, "thread_id": story.get("thread_id") or str(uuid.uuid4()), **story})
        for s in sources:
            self.story_sources.append({"id": str(uuid.uuid4()), **s, "story_id": sid})
        return sid

    def update_story(self, story_id, fields):
        for s in self.stories:
            if s["id"] == story_id:
                s.update(fields)

    def glossary_all(self): return copy.deepcopy(self.glossary)

    def insert_glossary(self, entry):
        for g in self.glossary:
            if g["slug"] == entry["slug"]:
                return g["id"]
        gid = str(uuid.uuid4())
        self.glossary.append({"id": gid, **entry})
        return gid

    def link_glossary(self, links):
        self.glossary_links |= set(links)
