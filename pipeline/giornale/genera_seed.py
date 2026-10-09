"""Genera supabase/seed.sql a partire da seed_data.py.

Uso:  cd pipeline && python -m giornale.genera_seed
"""
from __future__ import annotations

from pathlib import Path

from . import seed_data as d


def q(value) -> str:
    """Letterale SQL sicuro."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def arr(values) -> str:
    if not values:
        return "'{}'::text[]"
    return "array[" + ", ".join(q(v) for v in values) + "]::text[]"


def build() -> str:
    out = [
        "-- Generato da pipeline/giornale/genera_seed.py — non modificare a mano.",
        "-- Prima di eseguirlo sostituisci LA_TUA_EMAIL con l'email con cui accederai al sito.",
        "",
        "insert into public.settings (id, newspaper_name, owner_email) values "
        "(1, 'Il Mio Giornale', 'LA_TUA_EMAIL') on conflict (id) do nothing;",
        "",
    ]
    for c in d.CATEGORIES:
        out.append(
            "insert into public.categories (slug, name, description, subtopics, keywords, priority, max_items) values ("
            f"{q(c['slug'])}, {q(c['name'])}, {q(c['description'])}, {arr(c['subtopics'])}, {arr(c['keywords'])}, "
            f"{c['priority']}, {c['max_items']}) on conflict (slug) do nothing;"
        )
    out.append("")
    for s in d.SOURCES:
        out.append(
            "insert into public.sources (name, feed_url, homepage, kind, language, allow_fulltext, exclude_title_regex, notes) values ("
            f"{q(s['name'])}, {q(s['feed_url'])}, {q(s['homepage'])}, {q(s['kind'])}, {q(s['language'])}, "
            f"{q(s['allow_fulltext'])}, {q(s.get('exclude_title_regex'))}, {q(s['notes'])}) on conflict (feed_url) do nothing;"
        )
    out.append("")
    for g in d.GLOSSARY:
        out.append(
            "insert into public.glossary (slug, term, aliases, simple_definition, explanation, example, related, origin, reviewed) values ("
            f"{q(g['slug'])}, {q(g['term'])}, {arr(g['aliases'])}, {q(g['simple_definition'])}, {q(g['explanation'])}, "
            f"{q(g['example'])}, {arr(g['related'])}, 'curata', true) on conflict (slug) do nothing;"
        )
    out.append("")
    return "\n".join(out)


def main() -> None:
    target = Path(__file__).resolve().parents[2] / "supabase" / "seed.sql"
    target.write_text(build(), encoding="utf-8")
    print(f"Scritto {target}")


if __name__ == "__main__":
    main()
