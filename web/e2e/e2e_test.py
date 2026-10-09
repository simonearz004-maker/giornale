"""Test completo del sito nel browser (Playwright), contro la replica locale di Supabase.

Prerequisiti (vedi README, sezione Sviluppo): PostgreSQL con schema+seed, PostgREST, fake_supabase.py,
dati di prova da seed_ui.py, sito compilato e servito su BASE.
Uso: python e2e_test.py [cartella_screenshot]
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("BASE", "http://localhost:4173/")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else "shots"
PSQL = os.getenv("PSQL", "psql -h /tmp -p 5544 -U postgres -d g -t -A -c")
os.makedirs(SHOTS, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("OK   " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))


def sql(q):
    return subprocess.run(PSQL.split() + [q], capture_output=True, text=True).stdout.strip()


def login(page, email="io@example.org", pw="prova-123"):
    page.goto(BASE)
    page.wait_for_selector("#login-form")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", pw)
    page.click("button[type=submit]")


with sync_playwright() as p:
    browser = p.chromium.launch()
    console_errors = []

    def new_page(vp, scale=1, scheme="light", track=True):
        ctx = browser.new_context(viewport=vp, device_scale_factor=scale, locale="it-IT", timezone_id="Europe/Rome",
                                  color_scheme=scheme)
        page = ctx.new_page()
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        if track:  # l'utente senza permessi produce volutamente risposte 406 dal database
            page.on("console", lambda m: m.type == "error" and "400" not in m.text and "INTERNET_DISCONNECTED" not in m.text
                    and console_errors.append(m.text))
        return ctx, page

    # ------------------------------------------------------------------ telefono
    ctx, page = new_page({"width": 390, "height": 844}, 2)
    login(page, pw="sbagliata")
    page.wait_for_selector("#login-error:not([hidden])")
    check("Login con password errata respinto", "non corrette" in page.inner_text("#login-error"))
    page.fill("input[name=password]", "prova-123")
    page.click("button[type=submit]")
    page.wait_for_selector(".masthead__name")
    page.wait_for_timeout(600)
    check("Homepage: notizie da non perdere", page.locator("#h-must").count() == 1)
    check("Homepage: notizie verificate e da confermare", page.locator(".story").count() == 7, str(page.locator(".story").count()))
    check("Homepage: sezione 'Da confermare' separata", "Indiscrezioni" in page.inner_text(".block--muted"))
    check("Homepage: categoria vuota dichiarata", "Nessuno sviluppo rilevante" in page.inner_text("main"))
    check("Homepage: data e ora di aggiornamento", "Aggiornato alle" in page.inner_text(".masthead"))
    check("Tabbar visibile su telefono", page.locator(".tabbar").is_visible())
    page.screenshot(path=f"{SHOTS}/telefono-home.png")

    # apertura notizia nel pannello, mantenendo la posizione
    page.mouse.wheel(0, 1400)
    page.wait_for_timeout(300)
    y_before = page.evaluate("scrollY")
    target = page.locator(".block a[data-open]").nth(4)
    title = target.inner_text()
    target.click()
    page.wait_for_selector(".sheet .article__title")
    page.wait_for_timeout(400)
    check("Notizia aperta nel pannello", page.inner_text(".sheet .article__title") == title)
    check("Indirizzo della notizia condivisibile", "#/notizia/" in page.url)
    page.screenshot(path=f"{SHOTS}/telefono-notizia.png")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    check("Chiusura del pannello torna allo stesso punto", abs(page.evaluate("scrollY") - y_before) < 5,
          f"{y_before} -> {page.evaluate('scrollY')}")
    check("Chiusura riporta all'indirizzo della home", not page.url.split("#")[-1].startswith("/notizia"))

    # notizia principale: tutte le parti
    page.goto(BASE)
    page.wait_for_selector(".story--lead")
    page.click(".story--lead a[data-open]")
    page.wait_for_selector(".sheet .sources")
    body = page.inner_text(".sheet")
    for part in ["Perché è importante", "Te lo spiego in parole semplici", "I numeri", "Il contesto", "Le puntate precedenti",
                 "Che cosa potrebbe succedere adesso", "Cosa dicono esattamente le fonti", "Fonti", "Concetti collegati",
                 "Come è stata verificata"]:
        check(f"Dettaglio: sezione «{part}»", part in body)
    hrefs = page.eval_on_selector_all(".sheet .sourcelist a", "els => els.map(e => [e.href, e.target, e.rel])")
    check("Fonti: link diretti, in nuova scheda, sicuri", hrefs and all(h[0].startswith("https://") and h[1] == "_blank"
                                                                     and "noopener" in h[2] for h in hrefs), str(hrefs))
    page.locator(".sheet").screenshot(path=f"{SHOTS}/telefono-dettaglio-alto.png")
    page.evaluate("document.querySelector('.sheet__body').scrollTo(0, 700)")
    page.wait_for_timeout(200)
    page.screenshot(path=f"{SHOTS}/telefono-dettaglio-spiegazione.png")
    page.click("#btn-save")
    page.wait_for_timeout(500)
    check("Salvataggio notizia", page.get_attribute("#btn-save", "aria-pressed") == "true")
    page.keyboard.press("Escape")

    # persistenza: salvate e lette dopo ricaricamento
    page.reload()
    page.wait_for_selector(".story--lead")
    check("Indicatore 'Già letta' dopo la lettura", "Già letta" in page.inner_text(".story--lead"))
    page.goto(BASE + "#/salvate")
    page.wait_for_selector(".page__title")
    page.wait_for_timeout(500)
    check("Pagina Salvate dopo ricaricamento", page.locator(".story").count() == 1)
    page.goto(BASE + "#/cronologia")
    page.wait_for_timeout(700)
    check("Cronologia letture", page.locator(".story").count() >= 2)

    # glossario
    page.goto(BASE + "#/glossario")
    page.wait_for_selector("#gq")
    page.fill("#gq", "spread")
    visible = page.locator("#glist li:not([hidden])").count()
    check("Glossario: ricerca", visible == 1, str(visible))
    page.click("#glist li:not([hidden]) a")
    page.wait_for_selector(".entry")
    check("Glossario: voce collegata alle notizie", "Nelle notizie" in page.inner_text(".entry"))
    page.screenshot(path=f"{SHOTS}/telefono-glossario.png")

    # ricerca
    page.goto(BASE + "#/cerca?q=inflazione")
    page.wait_for_selector("#sresults .story, #sresults .empty", timeout=8000)
    check("Ricerca per parola chiave", page.locator("#sresults .story").count() >= 1)
    page.goto(BASE + "#/cerca?q=banca&cat=tecnologia")
    page.wait_for_timeout(800)
    check("Ricerca con filtro di categoria", page.locator("#sresults .story").count() == 0)

    # archivio
    page.goto(BASE + "#/archivio")
    page.wait_for_selector(".archive")
    check("Archivio: due edizioni", page.locator(".archive li").count() == 2)
    page.locator(".archive a").nth(1).click()
    page.wait_for_selector(".story")
    check("Archivio: edizione del giorno prima", "Attesa per la riunione" in page.inner_text("main"))

    # stato
    page.goto(BASE + "#/stato")
    page.wait_for_selector(".run")
    check("Stato: esecuzioni e notizie escluse", page.locator(".run").count() == 2 and "Notizie escluse" in page.inner_text("main"))

    # sezione con filtro date
    page.goto(BASE + "#/sezione/finanza-mercati")
    page.wait_for_selector(".story")
    n_all = page.locator(".story").count()
    page.fill("input[name=from]", "2026-10-10")
    page.click("#filters button[type=submit]")
    page.wait_for_timeout(600)
    check("Sezione: filtro per data", n_all == 2 and page.locator(".story").count() == 1, f"{n_all}")

    # offline: copia salvata con avviso
    page.goto(BASE)
    page.wait_for_selector(".story--lead")
    ctx.set_offline(True)
    page.goto(BASE + "#/sezioni")
    page.wait_for_timeout(200)
    page.evaluate("location.hash = '#/'")
    page.wait_for_selector(".story--lead", timeout=8000)
    page.wait_for_timeout(500)
    check("Offline: si legge la copia salvata con avviso", page.locator("#offline-banner").is_visible()
          and "offline" in page.inner_text("#offline-banner"))
    page.screenshot(path=f"{SHOTS}/telefono-offline.png")
    ctx.set_offline(False)
    ctx.close()

    # ------------------------------------------------------------------ computer
    ctx, page = new_page({"width": 1366, "height": 900})
    login(page)
    page.wait_for_selector(".story--lead")
    page.wait_for_timeout(500)
    check("Computer: menu delle sezioni in alto", page.locator(".topnav a").count() == 8)
    check("Computer: colonna 'Concetti di oggi'", page.locator(".home__side .marker").count() >= 3)
    page.screenshot(path=f"{SHOTS}/computer-home.png")
    page.locator(".block a[data-open]").nth(2).click()
    page.wait_for_selector(".sheet .article__title")
    page.wait_for_timeout(400)
    page.screenshot(path=f"{SHOTS}/computer-notizia.png")
    page.go_back()
    page.wait_for_timeout(400)
    check("Tasto Indietro chiude il pannello", page.locator("#sheet-root.open").count() == 0)

    # impostazioni: modifiche persistenti
    page.goto(BASE + "#/impostazioni")
    page.wait_for_selector("#s-name")
    page.fill("#s-name", "Il Caffè Economico")
    page.press("#s-name", "Tab")
    page.wait_for_timeout(700)
    check("Impostazioni: nome nel menu", page.inner_text(".brand") == "Il Caffè Economico")
    page.check("input[name=hour][value='8']")
    page.wait_for_timeout(600)
    page.select_option(".cat[data-id] select[data-f=priority] >> nth=7", "5")
    page.wait_for_timeout(600)
    page.fill("#add-excl input[name=w]", "calciomercato")
    page.click("#add-excl button")
    page.wait_for_timeout(600)
    page.click(".adder summary >> nth=0")
    page.fill("#new-cat input[name=name]", "Energia")
    page.fill("#new-cat textarea[name=subtopics]", "Prezzo del gas\nRinnovabili")
    page.fill("#new-cat input[name=keywords]", "gas, bollette")
    page.click("#new-cat button[type=submit]")
    page.wait_for_timeout(1200)
    check("Impostazioni: nuova sezione nel menu", "Energia" in page.inner_text(".topnav"))
    page.click("input[name=theme][value=dark]")
    page.click("input[name=size][value=l]")
    page.wait_for_timeout(500)
    page.screenshot(path=f"{SHOTS}/computer-impostazioni-scuro.png")
    page.reload()
    page.wait_for_selector(".masthead__name, #s-name")
    check("Preferenze salvate nel database",
          sql("select newspaper_name||'|'||array_to_string(update_hours,',')||'|'||array_to_string(excluded_topics,',') from settings")
          == "Il Caffè Economico|7,8|calciomercato",
          sql("select newspaper_name, update_hours, excluded_topics from settings"))
    check("Categoria personalizzata salvata", sql("select subtopics::text from categories where name='Energia'") == "{\"Prezzo del gas\",Rinnovabili}")
    check("Tema scuro e testo grande mantenuti", page.evaluate("[document.documentElement.dataset.theme, document.documentElement.dataset.size]") == ["dark", "l"])
    page.goto(BASE)
    page.wait_for_selector(".story--lead")
    page.wait_for_timeout(400)
    page.screenshot(path=f"{SHOTS}/computer-home-scuro.png")
    page.goto(BASE + "#/impostazioni")
    page.wait_for_selector(".cat")
    page.on("dialog", lambda d: d.accept())
    energia = page.locator(".cat", has=page.locator("strong", has_text=re.compile("^Energia$")))
    energia.locator("summary").click()
    energia.locator("[data-delete]").click()
    page.wait_for_timeout(1000)
    check("Eliminazione sezione", sql("select count(*) from categories where name='Energia'") == "0")
    page.click("input[name=theme][value=auto]")
    page.click("input[name=size][value=m]")
    page.wait_for_timeout(300)
    ctx.close()

    # link diretto a una notizia
    ctx, page = new_page({"width": 390, "height": 844}, 2, "dark")
    login(page)
    page.wait_for_selector(".story--lead")
    sid = page.get_attribute(".story--lead", "data-story")
    page.goto(BASE + f"#/notizia/{sid}")
    page.reload()
    page.wait_for_selector("#story-page .article__title")
    check("Link diretto a una notizia", page.locator("#story-page .sources").count() == 1)
    page.goto(BASE)
    page.wait_for_selector(".story--lead")
    page.wait_for_timeout(400)
    page.screenshot(path=f"{SHOTS}/telefono-home-scuro.png")
    ctx.close()

    # un altro utente registrato non vede nulla
    ctx, page = new_page({"width": 390, "height": 844}, track=False)
    login(page, "intruso@example.org")
    page.wait_for_selector(".notice--error")
    check("Altro utente: nessun accesso ai contenuti", "non riesco a leggere il giornale" in page.inner_text("body"))
    ctx.close()
    browser.close()

check("Nessun errore JavaScript", not console_errors, "; ".join(console_errors[:5]))
failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} controlli superati")
sys.exit(1 if failed else 0)
