"""Test della pipeline. Nessuna chiamata reale: feed, siti e modello sono simulati.

I contenuti di questi test sono FITTIZI e servono solo a verificare i controlli.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from giornale import prompts
from giornale.config import Config
from giornale.feeds import FeedResult, Item, parse_feed
from giornale.llm import (LLM, AllModelsExhausted, BudgetExhausted, GeminiProvider, ModelExhausted, parse_json)
from giornale.run import gate, run_pipeline
from giornale.schemas import Scheda
from giornale.store import MemoryStore
from giornale.textutil import canonical_url, number_index, unsupported_numbers
from giornale.cluster import cluster_items
from giornale.verify import check_card, verification_level

NOW = datetime(2026, 10, 10, 5, 10, tzinfo=timezone.utc)   # 07:10 a Roma
TODAY = date(2026, 10, 10)


# ---------------------------------------------------------------------------
# Testo e numeri
# ---------------------------------------------------------------------------
def test_numeri_supportati_e_inventati():
    idx = number_index(["L'inflazione è salita al 2,4% a settembre 2026, dal 2,1% di agosto. Spread a 120 punti base."])
    assert unsupported_numbers("Inflazione al 2,4%, spread a 120 punti", idx) == []
    assert unsupported_numbers("Inflazione al 2,7%", idx) == ["2,7"]
    # formato inglese nella fonte, italiano nella scheda
    idx2 = number_index(["Revenue rose to 1,234.5 million dollars"])
    assert unsupported_numbers("ricavi a 1.234,5 milioni", idx2) == []


def test_numeri_piccoli_e_sigle_ignorati():
    idx = number_index(["nessun numero"])
    assert unsupported_numbers("Il G7 si riunirà con 3 ministri", idx) == []
    assert unsupported_numbers("tagliati 3 punti", idx) == ["3"]      # con unità: si controlla


def test_url_canonico():
    a = canonical_url("https://www.ansa.it/sito/notizie/x.html?utm_source=rss&id=4#top")
    b = canonical_url("https://ansa.it/sito/notizie/x.html?id=4")
    assert a == b


def test_raggruppamento():
    mk = lambda t, src: Item("s", src, "testata", True, False, t, f"https://{src}.it/{abs(hash(t))}", "", NOW)
    items = [mk("La Bce taglia i tassi di interesse di 25 punti base", "ansa"),
             mk("Bce, tagliati i tassi di interesse di 25 punti base", "ilpost"),
             mk("Stellantis presenta il nuovo piano industriale", "ansa")]
    clusters = cluster_items(items)
    sizes = sorted(len(c.items) for c in clusters)
    assert sizes == [1, 2]


def test_feed_parsing_e_esclusione_regex():
    xml = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title><link>x</link><description>d</description>
    <item><title>CIG 123 - Fornitura</title><link>https://istat.it/a</link><pubDate>Sat, 10 Oct 2026 06:00:00 +0200</pubDate></item>
    <item><title>Inflazione settembre</title><link>https://istat.it/b</link><description>&lt;p&gt;Testo&lt;/p&gt;</description>
    <pubDate>Sat, 10 Oct 2026 06:00:00 +0200</pubDate></item></channel></rss>"""
    src = {"id": "1", "name": "ISTAT", "kind": "primaria", "allow_fulltext": True, "exclude_title_regex": r"^\s*CIG\b"}
    items = parse_feed(src, xml)
    assert [i.title for i in items] == ["Inflazione settembre"]
    assert items[0].summary == "Testo"
    assert items[0].published == datetime(2026, 10, 10, 4, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Controlli sulle schede
# ---------------------------------------------------------------------------
MATERIALS = [
    {"ref": "S1", "source_name": "ISTAT", "title": "Prezzi al consumo settembre 2026", "url": "https://www.istat.it/x",
     "published": "2026-10-10 07:00", "text": "A settembre 2026 l'inflazione è al 2,4%, dal 2,1% di agosto.",
     "fulltext": True, "kind": "primaria"},
    {"ref": "S2", "source_name": "ANSA", "title": "Istat, inflazione al 2,4%", "url": "https://www.ansa.it/y",
     "published": "2026-10-10 07:10", "text": "L'inflazione sale al 2,4% secondo l'Istat.", "fulltext": True,
     "kind": "testata"},
]


def good_card(**over) -> dict:
    card = {
        "titolo": "L'inflazione sale al 2,4% a settembre",
        "sintesi": "Secondo i dati dell'ISTAT, a settembre 2026 i prezzi al consumo sono cresciuti del 2,4% su base annua, "
                   "in aumento rispetto al 2,1% di agosto. È un dato che conta per il potere d'acquisto delle famiglie.",
        "perche_importa": [{"per_chi": "famiglie", "testo": "I prezzi crescono più in fretta di agosto.", "stato": "osservato",
                            "fonti": ["S1"]}],
        "spiegazione": {"titolo": "Che cos'è l'inflazione", "testo": "Esempio: con il 3% ciò che costava 100 ne costa 103."},
        "dati": [{"etichetta": "Inflazione", "valore": "2,4%", "periodo": "settembre 2026", "fonte": "S1"}],
        "contesto": "", "prossimi_passi": [],
        "affermazioni": [{"testo": "L'inflazione è al 2,4% a settembre", "fonti": ["S1", "S2"], "natura": "fatto"}],
        "divergenze": "", "data_evento": "2026-10-10", "termini": ["inflazione"],
        "indiscrezione": False, "materiale_insufficiente": False,
    }
    card.update(over)
    return card


def test_scheda_valida_passa():
    assert check_card(Scheda(**good_card()), MATERIALS, [], TODAY) == []


def test_numero_inventato_bloccato():
    errs = check_card(Scheda(**good_card(titolo="L'inflazione sale al 2,9% a settembre")), MATERIALS, [], TODAY)
    assert any("2,9" in e for e in errs)


def test_fonte_inesistente_e_affermazione_senza_fonte():
    card = good_card(affermazioni=[{"testo": "x", "fonti": ["S9"]}, {"testo": "y", "fonti": []}])
    errs = check_card(Scheda(**card), MATERIALS, [], TODAY)
    assert any("S9" in e for e in errs) and any("senza fonte" in e for e in errs)


def test_notizia_vecchia_bloccata():
    errs = check_card(Scheda(**good_card(data_evento="2026-09-01")), MATERIALS, [], TODAY)
    assert any("vecchio" in e for e in errs)


def test_livelli_di_verifica():
    card = Scheda(**good_card())
    assert verification_level(card, MATERIALS, False)[0] == "fonte_primaria"
    only_news = [dict(MATERIALS[1]), dict(MATERIALS[1], ref="S3", url="https://www.ilpost.it/z", source_name="Il Post")]
    c2 = Scheda(**good_card(affermazioni=[{"testo": "a", "fonti": ["S2", "S3"]}], dati=[]))
    assert verification_level(c2, only_news, False)[0] == "confermata"
    c3 = Scheda(**good_card(affermazioni=[{"testo": "a", "fonti": ["S2"]}], dati=[]))
    assert verification_level(c3, [MATERIALS[1]], False)[0] == "fonte_singola"
    assert verification_level(card, MATERIALS, True)[0] == "non_confermata"


# ---------------------------------------------------------------------------
# Modello: catena di riserva, budget, Gemini simulato
# ---------------------------------------------------------------------------
class FakeProvider:
    def __init__(self, name, fn):
        self._name, self.fn = name, fn

    @property
    def name(self):
        return self._name

    def generate(self, system, user, sleep=None):
        return self.fn(system, user)


def _exhausted(system, user):
    raise ModelExhausted("quota")


def test_passaggio_al_modello_di_riserva():
    llm = LLM([FakeProvider("a", _exhausted), FakeProvider("b", lambda s, u: '{"fedele": true}')],
              max_requests=5, min_interval=0, sleep=lambda s: None)
    from giornale.schemas import Controllo
    res, name = llm.json("x", "y", Controllo)
    assert res.fedele and name == "b" and "a" in llm.dead


def test_tutti_esauriti_e_budget():
    from giornale.schemas import Controllo
    llm = LLM([FakeProvider("a", _exhausted)], max_requests=5, min_interval=0, sleep=lambda s: None)
    with pytest.raises(AllModelsExhausted):
        llm.json("x", "y", Controllo)
    llm2 = LLM([FakeProvider("a", lambda s, u: '{"fedele": true}')], max_requests=1, min_interval=0, sleep=lambda s: None)
    llm2.json("x", "y", Controllo)
    with pytest.raises(BudgetExhausted):
        llm2.json("x", "y", Controllo)


def test_gemini_risposta_e_quota_giornaliera():
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert request.headers["x-goog-api-key"] == "k"
        if "gemini-ok" in str(request.url):
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": "ragionamento", "thought": True}, {"text": '{"fedele": true}'}]}}]})
        return httpx.Response(429, text='{"error": {"message": "Quota exceeded for metric GenerateRequestsPerDay"}}')
    client = httpx.Client(transport=httpx.MockTransport(handler))
    ok = GeminiProvider("k", "gemini-ok", client)
    assert parse_json(ok.generate("s", "u", sleep=lambda s: None)) == {"fedele": True}
    with pytest.raises(ModelExhausted):
        GeminiProvider("k", "gemini-ko", client).generate("s", "u", sleep=lambda s: None)


# ---------------------------------------------------------------------------
# Orario
# ---------------------------------------------------------------------------
def _store():
    return MemoryStore(
        settings={"owner_email": "io@example.org", "update_hours": [7], "max_requests_per_run": 40},
        categories=[{"slug": "economia-italiana", "name": "Economia italiana", "priority": 5, "max_items": 3,
                     "subtopics": [], "keywords": []},
                    {"slug": "banche", "name": "Banche", "priority": 4, "max_items": 3, "subtopics": [], "keywords": []}],
        sources=[{"name": "ISTAT", "feed_url": "https://www.istat.it/feed/", "kind": "primaria", "allow_fulltext": True},
                 {"name": "ANSA – Economia", "feed_url": "https://www.ansa.it/e.xml", "kind": "testata",
                  "allow_fulltext": True}],
        glossary=[{"slug": "inflazione", "term": "Inflazione", "aliases": ["prezzi al consumo"]}])


def test_orario():
    store = _store()
    s = store.get_settings()
    from zoneinfo import ZoneInfo
    rome = ZoneInfo("Europe/Rome")
    at = lambda h: datetime(2026, 10, 10, h, 10, tzinfo=rome)
    assert gate(store, s, at(6), False)[0] is False
    assert gate(store, s, at(7), False)[:2] == (True, "2026-10-10T07")
    assert gate(store, s, at(10), False)[0] is True            # recupero se l'esecuzione delle 7 è saltata
    assert gate(store, s, at(14), False)[0] is False           # oltre la finestra di recupero
    store.create_run({"slot": "2026-10-10T07", "status": "success"})
    assert gate(store, s, at(8), False)[0] is False            # già pubblicata
    assert gate(store, s, at(8), True)[0] is True              # esecuzione manuale


# ---------------------------------------------------------------------------
# Pipeline completa (simulata)
# ---------------------------------------------------------------------------
def _items():
    pub = NOW - timedelta(hours=1)
    return {
        "ISTAT": [Item("", "ISTAT", "primaria", True, False, "Prezzi al consumo settembre 2026",
                       "https://www.istat.it/x", "Inflazione al 2,4%", pub)],
        "ANSA – Economia": [Item("", "ANSA", "testata", True, False, "Istat, inflazione al 2,4% a settembre",
                                 "https://www.ansa.it/y", "Inflazione al 2,4%", pub),
                            Item("", "ANSA", "testata", True, False, "Banca X, indiscrezioni su una fusione",
                                 "https://www.ansa.it/z", "Secondo fonti, trattative in corso", pub),
                            Item("", "ANSA", "testata", True, False, "Vecchia notizia di tre giorni fa",
                                 "https://www.ansa.it/old", "", NOW - timedelta(days=3))]}


def _fetcher(store):
    by_name = _items()

    def fetch(sources):
        res = []
        for s in sources:
            its = by_name.get(s["name"], [])
            for i in its:
                i.source_id = s["id"]
            res.append(FeedResult(s, its, "ok"))
        return res
    return fetch


class FakeReader:
    def read(self, url, allow):
        texts = {"https://www.istat.it/x": MATERIALS[0]["text"] + " " * 300,
                 "https://www.ansa.it/y": MATERIALS[1]["text"] + " " * 300}
        t = texts.get(url, "")
        return (t.strip(), True) if t else ("", False)


def _script(invent_number_in_bank=True):
    def fn(system, user):
        if system == prompts.SELECTION_SYSTEM:
            lines = [l for l in user.splitlines() if l.startswith("C")]
            infl = [l.split(" |")[0] for l in lines if "nflazione" in l or "Prezzi" in l]
            bank = [l.split(" |")[0] for l in lines if "Banca X" in l]
            assert not any("Vecchia notizia" in l for l in lines), "le notizie vecchie non devono arrivare al modello"
            return json.dumps({"eventi": [
                {"gruppi": infl, "categoria": "economia-italiana", "rilevanza": 5, "motivo": "dato ufficiale"},
                {"gruppi": bank, "categoria": "banche", "rilevanza": 4, "motivo": "possibile fusione", "indiscrezione": True},
                {"gruppi": ["C99"], "categoria": "banche", "rilevanza": 5},           # gruppo inesistente: ignorato
            ]})
        if system == prompts.CARD_SYSTEM:
            if "Banca X" in user:
                return json.dumps(good_card(titolo="Banca X tratta una fusione da 7,5 miliardi",
                                            affermazioni=[{"testo": "trattative", "fonti": ["S1"]}], dati=[],
                                            data_evento=None, termini=["fusione"]))
            return json.dumps(good_card())
        if system == prompts.CHECK_SYSTEM:
            return '{"fedele": true, "problemi": []}'
        if system == prompts.GLOSSARY_SYSTEM:
            return '{"voci": []}'
        if system == prompts.REVIEW_SYSTEM:
            return '{"esiti": []}'
        raise AssertionError("prompt inatteso")
    return fn


def test_pipeline_completa():
    store = _store()
    cfg = Config(force=False)
    llm_factory = lambda n: LLM([FakeProvider("fake-flash", _script())], max_requests=n, min_interval=0,
                                sleep=lambda s: None)
    out = run_pipeline(store, cfg, fetcher=_fetcher(store), reader=FakeReader(), llm_factory=llm_factory, now_utc=NOW)
    assert out is not None
    # una notizia pubblicata (inflazione), una esclusa (numero inventato anche dopo il nuovo tentativo)
    assert len(store.stories) == 1, out.rejections
    st = store.stories[0]
    assert st["verification_level"] == "fonte_primaria"
    assert st["is_must_read"] is True
    assert {s["ref"] for s in store.story_sources} == {"S1", "S2"}
    assert any("7,5" in r["motivo"] for r in out.rejections)
    assert store.runs[-1]["status"] == "success"
    assert store.glossary_links, "il termine 'inflazione' va collegato al glossario"
    ed = store.editions[0]
    assert ed["notes"]["empty_categories"] == ["banche"]
    # seconda esecuzione nello stesso orario: non riparte
    assert run_pipeline(store, cfg, fetcher=_fetcher(store), reader=FakeReader(), llm_factory=llm_factory,
                        now_utc=NOW + timedelta(minutes=50)) is None


def test_fonti_tutte_irraggiungibili():
    store = _store()
    fetch = lambda sources: [FeedResult(s, [], "errore", "Timeout") for s in sources]
    out = run_pipeline(store, Config(force=True), fetcher=fetch, reader=FakeReader(),
                       llm_factory=lambda n: pytest.fail("il modello non va chiamato"), now_utc=NOW)
    assert out.status == "failed"
    assert store.stories == [] and store.editions == []
    assert all(s["consecutive_failures"] == 1 for s in store.sources)


def test_quota_esaurita_durante_la_selezione():
    store = _store()
    out = run_pipeline(store, Config(force=True), fetcher=_fetcher(store), reader=FakeReader(),
                       llm_factory=lambda n: LLM([FakeProvider("a", _exhausted)], n, 0, sleep=lambda s: None),
                       now_utc=NOW)
    assert out.status == "failed" and store.stories == []
    assert any("Selezione non riuscita" in e for e in out.errors)


def test_controllo_fedelta_negativo_esclude():
    store = _store()

    def fn(system, user):
        if system == prompts.CHECK_SYSTEM:
            return '{"fedele": false, "problemi": [{"campo": "sintesi", "testo": "x", "motivo": "non nelle fonti"}]}'
        return _script()(system, user)
    out = run_pipeline(store, Config(force=True), fetcher=_fetcher(store), reader=FakeReader(),
                       llm_factory=lambda n: LLM([FakeProvider("f", fn)], n, 0, sleep=lambda s: None), now_utc=NOW)
    assert store.stories == []
    assert any("fedeltà" in r["motivo"] for r in out.rejections)


def test_tetto_di_tempo():
    """Superato il tempo massimo, la pipeline chiude con ciò che ha già verificato."""
    from giornale import run as runmod
    store = _store()
    ticks = iter([0] + [10_000] * 50)   # avvio, poi tempo già scaduto alla prima notizia
    orig = runmod._execute

    def patched(*a, **kw):
        return orig(*a, clock=lambda: next(ticks), **kw)
    runmod._execute = patched
    try:
        out = run_pipeline(store, Config(force=True), fetcher=_fetcher(store), reader=FakeReader(),
                           llm_factory=lambda n: LLM([FakeProvider("f", _script())], n, 0, sleep=lambda s: None),
                           now_utc=NOW)
    finally:
        runmod._execute = orig
    assert out.status == "partial" and store.stories == []
    assert any("Tempo massimo" in e for e in out.errors)
    assert any("in tempo" in r["motivo"] for r in out.rejections)
    assert store.editions, "l'edizione resta registrata anche se parziale"
