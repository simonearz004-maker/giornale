"""Raccolta dei feed RSS/Atom e registrazione dello stato di ogni fonte."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

import feedparser
import httpx

from .textutil import canonical_url, clean_html, domain


@dataclass
class Item:
    source_id: str
    source_name: str
    source_kind: str            # primaria | testata
    allow_fulltext: bool
    preferred: bool
    title: str
    url: str
    summary: str
    published: datetime | None
    key: str = field(default="")          # url canonico

    def __post_init__(self):
        self.key = canonical_url(self.url)

    @property
    def domain(self) -> str:
        return domain(self.url)


@dataclass
class FeedResult:
    source: dict
    items: list[Item]
    status: str                 # ok | vuoto | errore
    error: str | None = None


def _entry_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        st = entry.get(attr)
        if st:
            try:
                # feedparser restituisce le date già convertite in UTC
                return datetime(*st[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def parse_feed(source: dict, content: bytes) -> list[Item]:
    parsed = feedparser.parse(content)
    rx = re.compile(source["exclude_title_regex"], re.I) if source.get("exclude_title_regex") else None
    items = []
    for e in parsed.entries:
        title = clean_html(e.get("title", ""))
        link = (e.get("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        if rx and rx.search(title):
            continue
        summary = clean_html(e.get("summary") or e.get("description") or "", limit=1200)
        items.append(Item(
            source_id=source["id"], source_name=source["name"], source_kind=source.get("kind", "testata"),
            allow_fulltext=bool(source.get("allow_fulltext", True)), preferred=bool(source.get("preferred")),
            title=title, url=link, summary=summary, published=_entry_date(e)))
    return items


def fetch_one(client: httpx.Client, source: dict) -> FeedResult:
    try:
        r = client.get(source["feed_url"])
        r.raise_for_status()
    except Exception as exc:  # rete, timeout, 4xx/5xx
        return FeedResult(source, [], "errore", f"{type(exc).__name__}: {str(exc)[:200]}")
    try:
        items = parse_feed(source, r.content)
    except Exception as exc:
        return FeedResult(source, [], "errore", f"Feed non leggibile: {str(exc)[:200]}")
    return FeedResult(source, items, "ok" if items else "vuoto")


def fetch_all(sources: list[dict], user_agent: str, timeout: float = 20.0) -> list[FeedResult]:
    headers = {"User-Agent": user_agent, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"}
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(lambda s: fetch_one(client, s), sources))


def filter_window(items: list[Item], since: datetime, now: datetime) -> list[Item]:
    """Tiene solo le voci con data nella finestra (le voci senza data vengono scartate:
    non si può dimostrare che siano recenti)."""
    out = []
    for it in items:
        if it.published is None:
            continue
        if since <= it.published <= now + _tolerance():
            out.append(it)
    return out


def _tolerance():
    from datetime import timedelta
    return timedelta(minutes=30)   # orologi dei server non perfettamente allineati


def filter_excluded(items: list[Item], excluded: list[str]) -> tuple[list[Item], int]:
    words = [w.strip().lower() for w in excluded if w and w.strip()]
    if not words:
        return items, 0
    kept, dropped = [], 0
    for it in items:
        text = f"{it.title} {it.summary}".lower()
        if any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words):
            dropped += 1
        else:
            kept.append(it)
    return kept, dropped


def dedupe(items: list[Item]) -> list[Item]:
    seen: dict[str, Item] = {}
    for it in items:
        if it.key not in seen:
            seen[it.key] = it
    return list(seen.values())
