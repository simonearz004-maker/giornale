"""Controlli automatici sulle schede, eseguiti dal codice (non dal modello)."""
from __future__ import annotations

from datetime import date, timedelta

from .schemas import Scheda
from .seed_data import PRIMARY_DOMAINS
from .textutil import domain, number_index, registered_domain, unsupported_numbers

VALID_STATO = {"osservato", "possibile"}
VALID_PASSO = {"ufficiale", "programmato", "previsione", "ipotesi"}
VALID_NATURA = {"fatto", "dichiarazione", "interpretazione"}
INSUFFICIENT = "materiale insufficiente"


def normalize_card(card: Scheda) -> Scheda:
    for i in card.perche_importa:
        if i.stato not in VALID_STATO:
            i.stato = "possibile"
    for p in card.prossimi_passi:
        if p.tipo not in VALID_PASSO:
            p.tipo = "ipotesi"
    for a in card.affermazioni:
        if a.natura not in VALID_NATURA:
            a.natura = "fatto"
    card.termini = [t.strip() for t in card.termini if t and t.strip()][:4]
    return card


def _index_for(materials: list[dict], previous: list[dict], today: date) -> set[str]:
    texts = []
    for m in materials:
        texts += [m["title"], m["text"], m.get("published") or ""]
    for p in previous:
        texts += [p["title"], p["summary"], p.get("date") or ""]
    texts.append(today.isoformat())
    texts.append(f"{today.day}/{today.month}/{today.year}")
    return number_index(texts)


def check_card(card: Scheda, materials: list[dict], previous: list[dict], today: date,
               is_update: bool = False) -> list[str]:
    if card.materiale_insufficiente:
        return [INSUFFICIENT]
    errors: list[str] = []
    s_refs = {m["ref"] for m in materials}
    p_refs = {p["ref"] for p in previous}
    all_refs = s_refs | p_refs

    if len(card.titolo.strip()) < 10:
        errors.append("Titolo mancante o troppo breve.")
    if len(card.sintesi.strip()) < 80:
        errors.append("Sintesi mancante o troppo breve.")
    if not card.affermazioni:
        errors.append("Mancano le affermazioni con le relative fonti.")

    for a in card.affermazioni:
        refs = set(a.fonti)
        if not refs:
            errors.append(f"Affermazione senza fonte: «{a.testo[:80]}».")
        elif not refs <= all_refs:
            errors.append(f"Fonte inesistente {sorted(refs - all_refs)} in «{a.testo[:80]}».")
        elif not refs & s_refs:
            errors.append(f"L'affermazione «{a.testo[:80]}» cita solo schede precedenti: serve una fonte di oggi.")
    for d in card.dati:
        if d.fonte not in s_refs:
            errors.append(f"Il dato «{d.etichetta}» cita una fonte non valida ({d.fonte}).")
    for group in (card.perche_importa, card.prossimi_passi):
        for x in group:
            bad = set(x.fonti) - all_refs
            if bad:
                errors.append(f"Fonte inesistente {sorted(bad)} in «{x.testo[:60]}».")

    # Numeri: devono comparire nei materiali.
    index = _index_for(materials, previous, today)
    fields = [("titolo", card.titolo), ("sintesi", card.sintesi), ("contesto", card.contesto),
              ("divergenze", card.divergenze)]
    fields += [("perché è importante", i.testo) for i in card.perche_importa]
    fields += [("dati", f"{d.valore} {d.periodo}") for d in card.dati]
    fields += [("prossimi passi", p.testo) for p in card.prossimi_passi]
    fields += [("affermazioni", a.testo) for a in card.affermazioni]
    for name, text in fields:
        missing = unsupported_numbers(text, index)
        if missing:
            errors.append(f"Numeri non presenti nelle fonti ({name}): {', '.join(missing)}.")

    # Date
    if card.data_evento:
        try:
            ev = date.fromisoformat(card.data_evento[:10])
            if ev > today + timedelta(days=1):
                errors.append(f"Data dell'evento nel futuro ({ev}).")
            elif ev < today - timedelta(days=10) and not is_update:
                errors.append(f"Fatto vecchio ({ev}): non va presentato come notizia del giorno.")
        except ValueError:
            card.data_evento = None
    return errors


def cited_refs(card: Scheda) -> set[str]:
    refs = set()
    for a in card.affermazioni:
        refs |= set(a.fonti)
    for d in card.dati:
        refs.add(d.fonte)
    for g in (card.perche_importa, card.prossimi_passi):
        for x in g:
            refs |= set(x.fonti)
    return refs


def is_primary(material: dict) -> bool:
    if material.get("kind") == "primaria":
        return True
    d = domain(material["url"])
    return any(d == p or d.endswith("." + p) for p in PRIMARY_DOMAINS)


def verification_level(card: Scheda, materials: list[dict], rumor: bool) -> tuple[str, list[str]]:
    if card.indiscrezione or rumor:
        return "non_confermata", ["Riportata come indiscrezione o senza conferma ufficiale."]
    refs = cited_refs(card)
    used = [m for m in materials if m["ref"] in refs] or materials
    notes = []
    full = [m["ref"] for m in used if m.get("fulltext")]
    partial = [m["ref"] for m in used if not m.get("fulltext")]
    if full:
        notes.append("Testo integrale letto per " + ", ".join(full) + ".")
    if partial:
        notes.append("Solo titolo e sommario del feed per " + ", ".join(partial) + ".")
    if any(is_primary(m) for m in used):
        return "fonte_primaria", notes
    domains = {registered_domain(m["url"]) for m in used}
    if len(domains) >= 2:
        return "confermata", notes + [f"Confermata da {len(domains)} testate indipendenti."]
    return "fonte_singola", notes + ["Una sola testata: nessuna conferma indipendente disponibile."]
