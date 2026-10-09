"""Inserisce nel database di PROVA un'edizione fittizia per testare l'interfaccia.

Tutti i contenuti sono inventati e marcati come «[Prova]»: servono solo a verificare
impaginazione e funzioni, non sono notizie. Uso: python seed_ui.py | psql ...
"""
import json
import uuid
from datetime import date, timedelta

TODAY = date.fromisoformat(__import__("os").getenv("UI_TODAY", "2026-10-10"))
YDAY = TODAY - timedelta(days=1)


def q(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, dict)):
        return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def arr(v):
    return "array[" + ",".join(q(x) for x in v) + "]::text[]" if v else "'{}'::text[]"


out = ["delete from glossary_story_links; delete from user_story_state; delete from story_sources; delete from stories;",
       "delete from editions; delete from runs;",
       "update settings set newspaper_name='Il Mio Giornale', update_hours='{7}' where id=1;"]

ed_today, ed_yday = str(uuid.uuid4()), str(uuid.uuid4())
REJ_TODAY = [{"titolo": "[Prova] Indiscrezione su una fusione bancaria",
              "motivo": "Controllo di fedeltà non superato: sintesi: «cifra dell'operazione» — non presente nelle fonti."}]
run_ok, run_partial = str(uuid.uuid4()), str(uuid.uuid4())
out.append(f"""insert into runs (id, started_at, finished_at, slot, status, models_used, requests_used, items_fetched, clusters,
 stories_published, stories_rejected, errors, rejections) values
 ({q(run_partial)}, '{YDAY}T05:07:00Z', '{YDAY}T05:21:00Z', '{YDAY}T07', 'partial', array['gemini-3.8-flash'], 41, 212, 140, 5, 2,
  {q(['Fonti non raggiungibili: CNBC – Economy'])},
  {q([{'titolo': '[Prova] Voce non confermata su un gruppo industriale', 'motivo': 'Controlli automatici non superati: Numeri non presenti nelle fonti (titolo): 4,2.'},
      {'titolo': '[Prova] Notizia con materiale scarso', 'motivo': 'Materiale insufficiente per una scheda affidabile.'}])}),
 ({q(run_ok)}, '{TODAY}T05:07:00Z', '{TODAY}T05:19:00Z', '{TODAY}T07', 'success', array['gemini-3.8-flash'], 38, 198, 131, 7, 1,
  '[]'::jsonb, {q(REJ_TODAY)});""")
out.append(f"insert into editions (id, edition_date, published_at, updated_at, last_run_id, notes) values "
           f"({q(ed_today)}, '{TODAY}', '{TODAY}T05:19:00Z', '{TODAY}T05:19:00Z', {q(run_ok)}, {q({'empty_categories': ['imprese'], 'feed_errors': []})}),"
           f"({q(ed_yday)}, '{YDAY}', '{YDAY}T05:21:00Z', '{YDAY}T05:21:00Z', {q(run_partial)}, '{{}}'::jsonb);")

NOTE = "Contenuto di prova per il test dell'interfaccia: non è una notizia reale."
thread = str(uuid.uuid4())

stories = [
    dict(ed=ed_today, d=TODAY, cat="finanza-mercati", rel=5, must=True, level="fonte_primaria", thread=thread, upd=True,
         title="[Prova] La banca centrale lascia i tassi fermi e apre a un taglio",
         summary=f"{NOTE} Nella riunione di oggi il consiglio della banca centrale ha lasciato invariato il tasso sui depositi al 2,00%. "
                 "Nel comunicato si legge che i prossimi passi dipenderanno dai dati sull'inflazione dei prossimi mesi. "
                 "Lo spread tra titoli italiani e tedeschi è sceso a 98 punti base dopo l'annuncio.",
         why=[{"chi": "famiglie", "testo": "Le rate dei mutui a tasso variabile restano stabili nel breve periodo.", "stato": "osservato"},
              {"chi": "conti pubblici", "testo": "Uno spread più basso, se duraturo, riduce il costo delle nuove emissioni di titoli.", "stato": "possibile"}],
         explainer={"titolo": "Che cos'è lo spread BTP-Bund", "testo": "È la differenza tra il rendimento dei titoli di Stato italiani a 10 anni e quello dei titoli tedeschi. Si misura in punti base: 100 punti valgono un punto percentuale.\nEsempio: se il BTP rende il 3,6% e il Bund il 2,6%, lo spread è di 100 punti base. Quando scende, gli investitori considerano il debito italiano meno rischioso."},
         data=[{"etichetta": "Tasso sui depositi", "valore": "2,00%", "periodo": "dalla riunione di oggi", "fonte": "S1"},
               {"etichetta": "Spread BTP-Bund", "valore": "98 punti base", "periodo": "chiusura di oggi", "fonte": "S2"}],
         context="Nelle ultime riunioni la banca centrale aveva già fermato la serie di tagli iniziata l'anno precedente.",
         steps=[{"tipo": "programmato", "testo": "La prossima riunione è in calendario a dicembre.", "fonti": ["S1"]},
                {"tipo": "previsione", "testo": "Secondo gli analisti citati dalla testata, un taglio è possibile all'inizio del prossimo anno.", "fonti": ["S2"]}],
         claims=[{"testo": "Il tasso sui depositi resta al 2,00%", "fonti": ["S1"], "natura": "fatto"},
                 {"testo": "Lo spread è sceso a 98 punti base", "fonti": ["S2"], "natura": "fatto"},
                 {"testo": "La presidente ha detto che le decisioni dipenderanno dai dati", "fonti": ["S1", "S2"], "natura": "dichiarazione"}],
         terms=["spread", "tassi Bce"],
         notes=["Testo integrale letto per S1, S2.", ""],
         sources=[("S1", "BCE – comunicati e discorsi", "[Prova] Comunicato sulle decisioni di politica monetaria", "https://www.ecb.europa.eu/press/", True),
                  ("S2", "ANSA – Economia", "[Prova] Tassi fermi, spread in calo", "https://www.ansa.it/sito/notizie/economia/", False)]),
    dict(ed=ed_today, d=TODAY, cat="economia-italiana", rel=5, must=True, level="fonte_primaria",
         title="[Prova] Inflazione in leggero aumento a settembre secondo la stima preliminare",
         summary=f"{NOTE} La stima preliminare indica prezzi al consumo in crescita dell'1,8% su base annua, dall'1,6% di agosto. "
                 "A spingere sono soprattutto i servizi, mentre l'energia continua a calare.",
         why=[{"chi": "famiglie", "testo": "Il potere d'acquisto resta sotto pressione se i salari non tengono il passo.", "stato": "possibile"}],
         explainer=None, data=[{"etichetta": "Inflazione annua", "valore": "1,8%", "periodo": "settembre, stima preliminare", "fonte": "S1"},
                               {"etichetta": "Inflazione annua", "valore": "1,6%", "periodo": "agosto", "fonte": "S1"}],
         context="", steps=[{"tipo": "programmato", "testo": "Il dato definitivo è atteso a metà del mese prossimo.", "fonti": ["S1"]}],
         claims=[{"testo": "Prezzi in crescita dell'1,8% su base annua", "fonti": ["S1", "S2"], "natura": "fatto"}], terms=["inflazione"],
         notes=["Testo integrale letto per S1, S2."],
         sources=[("S1", "ISTAT", "[Prova] Prezzi al consumo, stima preliminare", "https://www.istat.it/", True),
                  ("S2", "Il Post", "[Prova] Inflazione a settembre", "https://www.ilpost.it/", False)]),
    dict(ed=ed_today, d=TODAY, cat="politica-italiana", rel=4, must=True, level="confermata",
         title="[Prova] Il Governo presenta il documento programmatico di bilancio",
         summary=f"{NOTE} Il Consiglio dei ministri ha approvato il documento che anticipa le linee della manovra. "
                 "La maggioranza parla di priorità al taglio delle tasse sul lavoro, l'opposizione chiede più risorse per la sanità.",
         why=[{"chi": "conti pubblici", "testo": "Il documento fissa il percorso del deficit che la Commissione europea dovrà valutare.", "stato": "possibile"}],
         explainer={"titolo": "Legge di Bilancio e documento programmatico", "testo": "Il documento programmatico è una sintesi che il Governo invia a Bruxelles prima della Legge di Bilancio vera e propria, che il Parlamento deve approvare entro il 31 dicembre."},
         data=[], context="", steps=[{"tipo": "ufficiale", "testo": "Il testo passerà ora all'esame del Parlamento.", "fonti": ["S1"]}],
         claims=[{"testo": "Il Consiglio dei ministri ha approvato il documento", "fonti": ["S1", "S2"], "natura": "fatto"},
                 {"testo": "La maggioranza indica come priorità il taglio delle tasse sul lavoro", "fonti": ["S1"], "natura": "dichiarazione"},
                 {"testo": "L'opposizione chiede più fondi per la sanità", "fonti": ["S2"], "natura": "dichiarazione"}],
         terms=["legge di bilancio", "deficit pubblico"], notes=["Confermata da 2 testate indipendenti."],
         sources=[("S1", "ANSA – Politica", "[Prova] Via libera al documento di bilancio", "https://www.ansa.it/sito/notizie/politica/", False),
                  ("S2", "Il Sole 24 Ore – Politica", "[Prova] Manovra, le prime cifre", "https://www.ilsole24ore.com/", False)]),
    dict(ed=ed_today, d=TODAY, cat="banche", rel=4, must=False, level="fonte_singola",
         title="[Prova] Un gruppo bancario rivede al rialzo gli obiettivi di utile",
         summary=f"{NOTE} Il gruppo ha comunicato di attendersi un utile annuo superiore alle previsioni di inizio anno, grazie al margine di interesse ancora elevato.",
         why=[{"chi": "investitori", "testo": "Utili più alti possono tradursi in dividendi maggiori.", "stato": "possibile"}],
         explainer=None, data=[], context="", steps=[], claims=[{"testo": "Obiettivi di utile rivisti al rialzo", "fonti": ["S1"], "natura": "fatto"}],
         terms=["margine di interesse"], notes=["Una sola testata: nessuna conferma indipendente disponibile."],
         sources=[("S1", "ANSA – Economia", "[Prova] Banca alza le stime", "https://www.ansa.it/sito/notizie/economia/", False)]),
    dict(ed=ed_today, d=TODAY, cat="politica-internazionale", rel=4, must=False, level="confermata",
         title="[Prova] Nuovo round di colloqui commerciali tra Unione europea e Stati Uniti",
         summary=f"{NOTE} Le delegazioni si incontreranno la prossima settimana per discutere i dazi su acciaio e alluminio. Entrambe le parti parlano di clima costruttivo.",
         why=[{"chi": "imprese", "testo": "Gli esportatori di metalli attendono di sapere se i dazi verranno ridotti.", "stato": "possibile"}],
         explainer={"titolo": "Come funziona un dazio", "testo": "È una tassa sulle merci importate. La paga l'importatore, ma il costo può ricadere sui consumatori o sugli esportatori stranieri."},
         data=[], context="", steps=[{"tipo": "programmato", "testo": "Incontro tra le delegazioni la prossima settimana.", "fonti": ["S1", "S2"]}],
         claims=[{"testo": "Colloqui fissati per la prossima settimana", "fonti": ["S1", "S2"], "natura": "fatto"}], terms=["dazio"],
         notes=["Confermata da 2 testate indipendenti."],
         sources=[("S1", "ANSA – Mondo", "[Prova] Ue-Usa, nuovi colloqui", "https://www.ansa.it/sito/notizie/mondo/", False),
                  ("S2", "Politico Europe", "[Test] EU-US trade talks", "https://www.politico.eu/", False)]),
    dict(ed=ed_today, d=TODAY, cat="tecnologia", rel=3, must=False, level="fonte_singola",
         title="[Prova] Un produttore di chip annuncia un nuovo stabilimento in Europa",
         summary=f"{NOTE} L'investimento dovrebbe creare alcune centinaia di posti di lavoro nei prossimi tre anni.",
         why=[], explainer=None, data=[], context="", steps=[], claims=[{"testo": "Annunciato un nuovo stabilimento", "fonti": ["S1"]}],
         terms=[], notes=[], sources=[("S1", "ANSA – Tecnologia", "[Prova] Nuovo impianto", "https://www.ansa.it/canale_tecnologia/", False)]),
    dict(ed=ed_today, d=TODAY, cat="banche", rel=3, must=False, level="non_confermata",
         title="[Prova] Indiscrezioni su possibili nozze tra due banche regionali",
         summary=f"{NOTE} Secondo indiscrezioni di stampa non confermate dalle banche, sarebbero in corso contatti preliminari.",
         why=[], explainer=None, data=[], context="", steps=[{"tipo": "ipotesi", "testo": "Nessuna delle due banche ha commentato.", "fonti": ["S1"]}],
         claims=[{"testo": "Contatti preliminari secondo indiscrezioni", "fonti": ["S1"], "natura": "interpretazione"}], terms=["fusione"],
         notes=["Riportata come indiscrezione o senza conferma ufficiale."],
         sources=[("S1", "la Repubblica – Economia", "[Prova] Banche, voci di fusione", "https://www.repubblica.it/economia/", False)]),
    dict(ed=ed_yday, d=YDAY, cat="finanza-mercati", rel=4, must=True, level="confermata", thread=thread,
         title="[Prova] Attesa per la riunione della banca centrale, mercati prudenti",
         summary=f"{NOTE} Alla vigilia della riunione le Borse europee hanno chiuso poco mosse.", why=[], explainer=None, data=[],
         context="", steps=[], claims=[{"testo": "Borse poco mosse", "fonti": ["S1"]}], terms=[], notes=[],
         sources=[("S1", "ANSA – Economia", "[Prova] Borse in attesa", "https://www.ansa.it/sito/notizie/economia/", False)]),
]

for s in stories:
    sid = str(uuid.uuid4())
    s["id"] = sid
    out.append(
        "insert into stories (id, edition_id, edition_date, category_id, category_slug, thread_id, is_update, title, summary, why_important,"
        " explainer, data_points, context, next_steps, claims, terms, relevance, is_must_read, verification_level, verification_notes,"
        " event_date, model_used) values ("
        f"{q(sid)}, {q(s['ed'])}, '{s['d']}', (select id from categories where slug={q(s['cat'])}), {q(s['cat'])},"
        f" {q(s.get('thread') or str(uuid.uuid4()))}, {q(s.get('upd', False))}, {q(s['title'])}, {q(s['summary'])}, {q(s['why'])},"
        f" {q(s['explainer']) if s['explainer'] else 'null'}, {q(s['data'])}, {q(s['context'])}, {q(s['steps'])}, {q(s['claims'])},"
        f" {arr(s['terms'])}, {s['rel']}, {q(s['must'])}, {q(s['level'])}, {q([n for n in s['notes'] if n])}, '{s['d']}', 'gemini-3.8-flash');")
    for ref, name, title, url, prim in s["sources"]:
        out.append("insert into story_sources (story_id, ref, source_name, title, url, published_at, is_primary, fulltext_used) values "
                   f"({q(sid)}, {q(ref)}, {q(name)}, {q(title)}, {q(url)}, '{s['d']}T04:30:00Z', {q(prim)}, {q(prim)});")

links = {"spread-btp-bund": 0, "tasso-sui-depositi-bce": 0, "inflazione": 1, "legge-di-bilancio": 2, "deficit-pubblico": 2,
         "margine-di-interesse": 3, "dazio": 4, "fusione-acquisizione": 6}
for slug, idx in links.items():
    out.append(f"insert into glossary_story_links (glossary_id, story_id) select id, {q(stories[idx]['id'])} from glossary where slug={q(slug)};")

print("\n".join(out))
