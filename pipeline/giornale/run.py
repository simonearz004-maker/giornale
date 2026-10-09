"""Esecuzione quotidiana: raccoglie, seleziona, scrive, verifica e salva le notizie.

Avvio:  cd pipeline && python -m giornale.run
Variabili: vedi config.py (FORCE_RUN=1 per eseguire subito, ignorando l'orario).
"""
from __future__ import annotations

import logging
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import prompts
from .articles import ArticleReader
from .cluster import Cluster, cluster_items
from .config import Config
from .feeds import FeedResult, Item, dedupe, fetch_all, filter_excluded, filter_window
from .llm import LLM, AllModelsExhausted, BudgetExhausted, LLMError, build_llm
from .schemas import Controllo, Revisione, Scheda, Selezione, Voci
from .store import BaseStore, SupabaseStore
from .textutil import jaccard, normalize, slugify, tokens
from .verify import INSUFFICIENT, check_card, cited_refs, is_primary, normalize_card, verification_level

log = logging.getLogger("giornale")

MAX_CLUSTERS_FOR_SELECTION = 220
MAX_MATERIALS = 4
CATCH_UP_HOURS = 6
MAX_ATTEMPTS_PER_SLOT = 3


# ---------------------------------------------------------------------------
# Orario
# ---------------------------------------------------------------------------
def gate(store: BaseStore, settings: dict, now_local: datetime, force: bool) -> tuple[bool, str, str]:
    """Decide se eseguire ora. Restituisce (esegui, slot, motivo)."""
    today = now_local.date().isoformat()
    if force:
        return True, f"{today}T{now_local.hour:02d}", "esecuzione manuale"
    hours = sorted({int(h) for h in settings.get("update_hours") or [7]})
    for h in hours:
        if not (h <= now_local.hour <= h + CATCH_UP_HOURS):
            continue
        slot = f"{today}T{h:02d}"
        runs = store.runs_for_slot(slot)
        if any(r["status"] in ("success", "partial") for r in runs):
            continue
        recent_running = [r for r in runs if r["status"] == "running" and
                          datetime.fromisoformat(r["started_at"].replace("Z", "+00:00")) >
                          datetime.now(timezone.utc) - timedelta(minutes=90)]
        if recent_running:
            return False, slot, "un'esecuzione è già in corso"
        if len([r for r in runs if r["status"] == "failed"]) >= MAX_ATTEMPTS_PER_SLOT:
            continue
        return True, slot, f"edizione delle {h:02d}:00"
    return False, "", "non è l'orario di aggiornamento"


# ---------------------------------------------------------------------------
# Supporto
# ---------------------------------------------------------------------------
@dataclass
class Outcome:
    status: str = "success"
    items_fetched: int = 0
    clusters: int = 0
    published: list[str] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    llm: LLM | None = None


def _fmt_local(dt: datetime | None, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M") if dt else ""


def _rank_clusters(clusters: list[Cluster]) -> list[Cluster]:
    def score(c: Cluster):
        primary = any(i.source_kind == "primaria" for i in c.items)
        preferred = any(i.preferred for i in c.items)
        newest = max(i.published.timestamp() for i in c.items if i.published)
        return (primary or len(c.domains) >= 2 or preferred, newest)
    return sorted(clusters, key=score, reverse=True)


def pick_materials(items: list[Item]) -> list[Item]:
    """Fino a 4 voci: prima le fonti primarie e preferite, poi testate diverse, poi le più recenti."""
    ordered = sorted(items, key=lambda i: (i.source_kind != "primaria", not i.preferred,
                                            -(i.published.timestamp() if i.published else 0)))
    chosen, domains = [], set()
    for it in ordered:                       # prima passata: un articolo per sito
        if it.domain not in domains:
            chosen.append(it)
            domains.add(it.domain)
        if len(chosen) == MAX_MATERIALS:
            return chosen
    for it in ordered:                       # seconda passata: completa
        if it not in chosen:
            chosen.append(it)
        if len(chosen) == MAX_MATERIALS:
            break
    return chosen


def build_materials(items: list[Item], reader: ArticleReader, tz: ZoneInfo) -> list[dict]:
    materials = []
    for n, it in enumerate(items, start=1):
        text, full = reader.read(it.url, it.allow_fulltext)
        if not text:
            text = it.summary or it.title
        materials.append({"ref": f"S{n}", "source_name": it.source_name, "title": it.title, "url": it.url,
                          "published": _fmt_local(it.published, tz), "published_dt": it.published,
                          "text": text, "fulltext": full, "kind": it.source_kind})
    return materials


def card_to_dict(card: Scheda) -> dict:
    return card.model_dump()


def _same_story(title: str, existing: list[dict]) -> bool:
    t = tokens(title)
    return any(jaccard(t, tokens(s["title"])) >= 0.6 for s in existing)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def run_pipeline(store: BaseStore, cfg: Config, *, fetcher=None, reader=None, llm_factory=None,
                 now_utc: datetime | None = None) -> Outcome | None:
    settings = store.get_settings()
    tz = ZoneInfo(settings.get("timezone") or "Europe/Rome")
    now_utc = now_utc or datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)

    proceed, slot, reason = gate(store, settings, now_local, cfg.force)
    if not proceed:
        log.info("Nessuna esecuzione: %s.", reason)
        return None
    log.info("Avvio: %s (slot %s).", reason, slot)

    run = store.create_run({"slot": slot, "trigger": cfg.trigger, "status": "running"})
    out = Outcome()
    try:
        _execute(store, cfg, settings, tz, now_utc, now_local, run, out,
                 fetcher or (lambda srcs: fetch_all(srcs, cfg.user_agent)),
                 reader or ArticleReader(cfg.user_agent),
                 llm_factory or (lambda n: build_llm(cfg, n)))
    except Exception as exc:  # errore imprevisto: si registra e si lascia intatta l'edizione precedente
        out.status = "failed"
        out.errors.append(f"Errore imprevisto: {type(exc).__name__}: {exc}")
        log.error(traceback.format_exc())
    finally:
        llm = out.llm
        store.update_run(run["id"], {
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": out.status,
            "models_used": llm.models_used if llm else [],
            "requests_used": llm.used if llm else 0,
            "items_fetched": out.items_fetched,
            "clusters": out.clusters,
            "stories_published": len(out.published),
            "stories_rejected": len(out.rejections),
            "errors": out.errors + (llm.notes if llm else []),
            "rejections": out.rejections,
        })
    log.info("Fine: %s — pubblicate %d, escluse %d.", out.status, len(out.published), len(out.rejections))
    return out


def _execute(store, cfg, settings, tz, now_utc, now_local, run, out: Outcome, fetcher, reader, llm_factory):
    today = now_local.date()
    categories = [c for c in store.list_categories() if c.get("enabled")]
    cat_by_slug = {c["slug"]: c for c in categories}
    sources = [s for s in store.list_sources() if s.get("enabled")]
    if not categories:
        out.errors.append("Nessuna categoria attiva.")
        out.status = "failed"
        return
    if not sources:
        out.errors.append("Nessuna fonte attiva.")
        out.status = "failed"
        return

    # 1. Raccolta e stato delle fonti
    results: list[FeedResult] = fetcher(sources)
    feed_errors = []
    for r in results:
        failures = (r.source.get("consecutive_failures") or 0) + 1 if r.status == "errore" else 0
        store.update_source(r.source["id"], {
            "last_status": r.status, "last_error": r.error, "last_item_count": len(r.items),
            "last_checked_at": now_utc.isoformat(), "consecutive_failures": failures})
        if r.status == "errore":
            feed_errors.append(r.source["name"])
    if feed_errors:
        out.errors.append("Fonti non raggiungibili: " + ", ".join(feed_errors))
    items = [i for r in results for i in r.items]
    if not items and len(feed_errors) == len(results):
        out.status = "failed"
        out.errors.append("Nessuna fonte raggiungibile: edizione non aggiornata.")
        return

    # 2. Finestra temporale, esclusioni, duplicati, notizie già usate
    last = store.last_good_run()
    since = now_utc - timedelta(hours=cfg.max_window_hours)
    if last:
        last_start = datetime.fromisoformat(last["started_at"].replace("Z", "+00:00"))
        since = max(since, last_start - timedelta(hours=2))
    since = min(since, now_utc - timedelta(hours=12))
    items = filter_window(items, since, now_utc)
    items, n_excl = filter_excluded(items, settings.get("excluded_topics") or [])
    used_urls = store.recent_source_urls(4)
    items = [i for i in dedupe(items) if i.url not in used_urls]
    out.items_fetched = len(items)
    edition = store.get_or_create_edition(today)
    existing = store.stories_for_edition(edition["id"])

    if not items:
        _finalize_edition(store, edition, run, categories, settings, feed_errors, now_utc)
        out.errors.append("Nessuna notizia nuova nella finestra temporale.")
        return

    clusters = _rank_clusters(cluster_items(items))[:MAX_CLUSTERS_FOR_SELECTION]
    out.clusters = len(clusters)
    by_id = {c.cid: c for c in clusters}

    # 3. Selezione
    recent = store.recent_stories(4)
    threads, thread_map = [], {}
    for n, s in enumerate(recent[:60], start=1):
        tid = f"T{n}"
        thread_map[tid] = s
        threads.append(f"{tid} | {s['edition_date']} | {s['category_slug']} | {s['title']}")

    llm = llm_factory(int(settings.get("max_requests_per_run") or 60))
    out.llm = llm
    try:
        selection, _ = llm.json(prompts.SELECTION_SYSTEM,
                                prompts.selection_user([c.describe() for c in clusters], categories,
                                                       settings.get("excluded_topics") or [], threads), Selezione)
    except (AllModelsExhausted, BudgetExhausted, LLMError) as exc:
        out.status = "failed"
        out.errors.append(f"Selezione non riuscita: {exc}")
        return

    events = []
    for ev in selection.eventi:
        ids = [g for g in ev.gruppi if g in by_id]
        if not ids or ev.categoria not in cat_by_slug or ev.rilevanza < cfg.min_relevance:
            continue
        ev.gruppi = ids
        events.append(ev)
    events.sort(key=lambda e: (-e.rilevanza, -cat_by_slug[e.categoria]["priority"]))

    # limite per categoria (contando le notizie già pubblicate oggi) e budget di richieste
    per_cat = {slug: sum(1 for s in existing if s["category_slug"] == slug) for slug in cat_by_slug}
    reserve_glossary = 2
    affordable = max(1, (llm.remaining - reserve_glossary) // 2)
    chosen, used_cluster_ids = [], set()
    for ev in events:
        if len(chosen) >= affordable:
            out.rejections.append({"titolo": by_id[ev.gruppi[0]].lead.title,
                                   "motivo": "Richieste al modello insufficienti per verificarla oggi."})
            continue
        if set(ev.gruppi) & used_cluster_ids:
            continue
        cat = cat_by_slug[ev.categoria]
        if per_cat[ev.categoria] >= cat["max_items"]:
            continue
        lead_title = by_id[ev.gruppi[0]].lead.title
        if _same_story(lead_title, existing):
            continue
        per_cat[ev.categoria] += 1
        used_cluster_ids |= set(ev.gruppi)
        chosen.append(ev)

    # 4. Scrittura e verifica
    for ev in chosen:
        cat = cat_by_slug[ev.categoria]
        ev_items = [i for cid in ev.gruppi for i in by_id[cid].items]
        lead_title = by_id[ev.gruppi[0]].lead.title
        try:
            materials = build_materials(pick_materials(ev_items), reader, tz)
            previous, thread_id, is_update = [], str(uuid.uuid4()), False
            if ev.seguito_di and ev.seguito_di in thread_map:
                base = thread_map[ev.seguito_di]
                thread_id, is_update = base["thread_id"], True
                same_thread = [s for s in recent if s["thread_id"] == base["thread_id"]][:2]
                previous = [{"ref": f"P{k}", "date": s["edition_date"], "title": s["title"], "summary": s["summary"]}
                            for k, s in enumerate(same_thread, start=1)]
            card, model_name, reason = _write_and_verify(llm, cat, materials, previous, today, is_update)
        except (AllModelsExhausted, BudgetExhausted) as exc:
            out.status = "partial"
            out.errors.append(f"Interrotto prima di completare tutte le notizie: {exc}")
            out.rejections.append({"titolo": lead_title, "motivo": "Quota del modello esaurita."})
            break
        except LLMError as exc:
            out.rejections.append({"titolo": lead_title, "motivo": f"Errore del modello: {exc}"})
            continue
        if card is None:
            out.rejections.append({"titolo": lead_title, "motivo": reason})
            continue

        level, notes = verification_level(card, materials, ev.indiscrezione)
        refs = cited_refs(card)
        story_sources = [{"ref": m["ref"], "source_name": m["source_name"], "title": m["title"], "url": m["url"],
                          "published_at": m["published_dt"].isoformat() if m["published_dt"] else None,
                          "is_primary": is_primary(m), "fulltext_used": m["fulltext"]}
                         for m in materials if m["ref"] in refs] or []
        story = {
            "edition_id": edition["id"], "edition_date": today.isoformat(),
            "category_id": cat["id"], "category_slug": cat["slug"],
            "thread_id": thread_id, "is_update": is_update,
            "title": card.titolo.strip(), "summary": card.sintesi.strip(),
            "why_important": [{"chi": i.per_chi, "testo": i.testo, "stato": i.stato} for i in card.perche_importa],
            "explainer": card.spiegazione.model_dump() if card.spiegazione else None,
            "data_points": [d.model_dump() for d in card.dati],
            "context": card.contesto.strip(),
            "next_steps": [p.model_dump() for p in card.prossimi_passi],
            "claims": [a.model_dump() for a in card.affermazioni],
            "divergences": card.divergenze.strip(),
            "terms": card.termini,
            "relevance": ev.rilevanza,
            "verification_level": level, "verification_notes": notes,
            "event_date": card.data_evento[:10] if card.data_evento else None,
            "model_used": model_name,
        }
        sid = store.insert_story(story, story_sources)
        existing.append({**story, "id": sid})
        out.published.append(sid)

    if out.status == "success" and not out.published and chosen:
        out.status = "partial"

    # 5. Notizie da non perdere
    _update_must_read(store, edition["id"], cat_by_slug, int(settings.get("max_must_read") or 5))

    # 6. Glossario
    try:
        _update_glossary(store, llm, [s for s in existing if s.get("id") in set(out.published)], cfg)
    except (AllModelsExhausted, BudgetExhausted, LLMError) as exc:
        out.errors.append(f"Glossario non aggiornato: {exc}")

    _finalize_edition(store, edition, run, categories, settings, feed_errors, now_utc)


def _write_and_verify(llm: LLM, cat: dict, materials, previous, today: date, is_update: bool):
    errors: list[str] = []
    for attempt in range(2):
        card, model_name = llm.json(prompts.CARD_SYSTEM,
                                    prompts.card_user(cat["name"], materials, previous, today.isoformat(),
                                                      errors or None), Scheda)
        card = normalize_card(card)
        errors = check_card(card, materials, previous, today, is_update)
        if errors == [INSUFFICIENT]:
            return None, model_name, "Materiale insufficiente per una scheda affidabile."
        if errors:
            if attempt == 0 and llm.remaining >= 2:
                continue
            return None, model_name, "Controlli automatici non superati: " + " ".join(errors[:4])
        ctrl, _ = llm.json(prompts.CHECK_SYSTEM, prompts.check_user(materials, previous, card_to_dict(card)), Controllo)
        if ctrl.fedele and not ctrl.problemi:
            return card, model_name, ""
        errors = [f"{p.campo}: «{p.testo[:120]}» — {p.motivo}" for p in ctrl.problemi] or ["Scheda giudicata non fedele."]
        if attempt == 0 and llm.remaining >= 2:
            continue
        return None, model_name, "Controllo di fedeltà non superato: " + " ".join(errors[:3])
    return None, "", "Controlli non superati."


def _update_must_read(store: BaseStore, edition_id: str, cat_by_slug: dict, limit: int):
    stories = store.stories_for_edition(edition_id)
    eligible = [s for s in stories if s["verification_level"] != "non_confermata" and s["relevance"] >= 4]
    eligible.sort(key=lambda s: (-s["relevance"], -(cat_by_slug.get(s["category_slug"], {}).get("priority", 0)),
                                 s.get("created_at") or ""))
    top = {s["id"] for s in eligible[:limit]}
    for s in stories:
        flag = s["id"] in top
        if bool(s.get("is_must_read")) != flag:
            store.update_story(s["id"], {"is_must_read": flag})


def _glossary_key(text: str) -> str:
    return slugify(text)


def _update_glossary(store: BaseStore, llm: LLM, new_stories: list[dict], cfg: Config):
    if not new_stories:
        return
    entries = store.glossary_all()
    index: dict[str, str] = {}
    for g in entries:
        for name in [g["slug"], g["term"], *(g.get("aliases") or [])]:
            index[_glossary_key(name)] = g["id"]
            # "Spread BTP-Bund" deve trovare anche "spread": si indicizza anche la parte prima della parentesi
            index[_glossary_key(name.split("(")[0])] = g["id"]

    links, missing = [], {}
    for s in new_stories:
        for term in s.get("terms") or []:
            gid = index.get(_glossary_key(term))
            if gid:
                links.append((gid, s["id"]))
            else:
                missing.setdefault(_glossary_key(term), (term, []))[1].append(s["id"])
    store.link_glossary(links)

    todo = list(missing.values())[: cfg.max_new_glossary_terms]
    if not todo or llm.remaining < 2:
        return
    voci, _ = llm.json(prompts.GLOSSARY_SYSTEM, "Termini: " + ", ".join(t for t, _ in todo), Voci)
    if not voci.voci:
        return
    review, _ = llm.json(prompts.REVIEW_SYSTEM, "Voci da controllare:\n" +
                         "\n".join(v.model_dump_json() for v in voci.voci), Revisione)
    ok = {normalize(e.termine) for e in review.esiti if e.corretta}
    story_ids_by_term = {k: ids for k, (_, ids) in missing.items()}
    for v in voci.voci:
        if normalize(v.termine) not in ok:
            continue
        slug = _glossary_key(v.termine)
        gid = store.insert_glossary({
            "slug": slug, "term": v.termine.strip(), "aliases": [],
            "simple_definition": v.definizione_semplice.strip(), "explanation": v.spiegazione.strip(),
            "example": v.esempio.strip(), "related": [_glossary_key(r) for r in v.correlati][:6],
            "origin": "generata", "reviewed": True})
        store.link_glossary([(gid, sid) for sid in story_ids_by_term.get(slug, [])])


def _finalize_edition(store, edition, run, categories, settings, feed_errors, now_utc):
    stories = store.stories_for_edition(edition["id"])
    present = {s["category_slug"] for s in stories}
    empty = [c["slug"] for c in categories if c["slug"] not in present and c.get("max_items", 0) > 0]
    store.update_edition(edition["id"], {
        "updated_at": now_utc.isoformat(), "last_run_id": run["id"],
        "notes": {"empty_categories": empty, "feed_errors": feed_errors}})


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config()
    missing = cfg.validate()
    if missing:
        log.error("Variabili mancanti: %s (impostale nei Secrets di GitHub).", ", ".join(missing))
        return 2
    store = SupabaseStore(cfg.supabase_url, cfg.supabase_key)
    out = run_pipeline(store, cfg)
    if out is None:
        return 0
    if out.errors:
        for e in out.errors:
            log.warning(e)
    return 1 if out.status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
