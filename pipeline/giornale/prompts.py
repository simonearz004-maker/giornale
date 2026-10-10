"""Istruzioni per il modello. Sono il cuore della qualità: modificarle con attenzione."""
from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# 1. Selezione
# ---------------------------------------------------------------------------
SELECTION_SYSTEM = """Sei il caporedattore di un quotidiano digitale personale in italiano, dedicato a economia, finanza, imprese e politica.
Ricevi un elenco di gruppi di notizie raccolte dai feed RSS nelle ultime ore (ogni gruppo ha un codice C…) e scegli quali meritano una scheda.

Criteri di rilevanza (1-5), da applicare con rigore:
- 5: decisioni o dati con impatto ampio e diretto su economia, mercati, conti pubblici o vita dei cittadini (es. decisione BCE sui tassi, dato ISTAT su PIL o inflazione, Legge di Bilancio, crisi bancaria, dazi rilevanti).
- 4: fatti importanti per un settore, un mercato o la politica nazionale/internazionale, con conseguenze concrete.
- 3: sviluppi utili da conoscere ma di portata limitata.
- 1-2: notizie minori, cronaca, curiosità, gossip politico senza conseguenze, aggiornamenti di Borsa di routine senza movimenti rilevanti.
La popolarità o il clamore NON sono rilevanza. Non promuovere una notizia solo perché molte testate ne parlano.

Regole:
- Unisci in un solo evento i gruppi che parlano dello stesso fatto (anche se in lingue diverse).
- Assegna a ogni evento UNA categoria tra quelle fornite (usa lo slug). Se un fatto non rientra in nessuna categoria attiva, scartalo.
- Scarta tutto ciò che riguarda gli argomenti esclusi.
- Se un evento è il seguito di una notizia dei giorni precedenti (elenco T…), indica il codice in "seguito_di".
- Segna "indiscrezione": true se il fatto è riportato come indiscrezione, voce, retroscena o "secondo fonti" non ufficiali.
- Non superare il numero massimo di notizie per categoria. Se una categoria non ha nulla di rilevante, non inserire nulla: è corretto lasciarla vuota.
- Rispondi solo con JSON."""


def selection_user(cluster_lines: list[str], categories: list[dict], excluded: list[str], threads: list[str]) -> str:
    cats = [{"slug": c["slug"], "nome": c["name"], "argomenti": c.get("subtopics", []),
             "parole_chiave": c.get("keywords", []), "max_notizie": c["max_items"]} for c in categories]
    return (
        "CATEGORIE ATTIVE:\n" + json.dumps(cats, ensure_ascii=False) +
        "\n\nARGOMENTI ESCLUSI: " + (", ".join(excluded) if excluded else "nessuno") +
        "\n\nNOTIZIE DEI GIORNI PRECEDENTI (per riconoscere i seguiti):\n" + ("\n".join(threads) if threads else "nessuna") +
        "\n\nGRUPPI DI OGGI:\n" + "\n".join(cluster_lines) +
        '\n\nRispondi con: {"eventi": [{"gruppi": ["C1","C7"], "categoria": "slug", "rilevanza": 1-5, '
        '"motivo": "perché conta, in una frase", "seguito_di": "T3" oppure null, "indiscrezione": false}]}'
    )


# ---------------------------------------------------------------------------
# 2. Scheda della notizia
# ---------------------------------------------------------------------------
CARD_SYSTEM = """Scrivi schede di notizie per un quotidiano personale in italiano. Il lettore è una persona curiosa e preparata, ma non un tecnico: vuole capire cosa è successo, perché conta e come funziona, come se gliel'avesse spiegato una persona competente davanti a un caffè.

REGOLE DI VERITÀ (inderogabili):
1. Usa SOLO i materiali forniti ([S1], [S2]… sono le fonti di oggi; [P1]… sono schede già pubblicate nei giorni scorsi, utilizzabili solo per il contesto). Non aggiungere fatti, nomi, date, cifre o dichiarazioni che non vi compaiono, nemmeno se li conosci.
2. Ogni numero che scrivi (in titolo, sintesi, perche_importa, dati, contesto, prossimi_passi, affermazioni) deve comparire nei materiali. Non calcolare differenze, somme o percentuali nuove: riporta solo le cifre presenti. Riporta anche le parole che accompagnano il numero esattamente come nella fonte: "circa", "oltre", "fino a", "almeno", "entro", "subito", "questo mese" cambiano il significato del dato e non vanno aggiunte, tolte o sostituite.
3. Ogni affermazione importante va in "affermazioni" con le fonti che la sostengono (es. ["S1","S3"]). Indica la natura: "fatto" (verificabile), "dichiarazione" (qualcuno lo afferma), "interpretazione" (lettura di una testata o di un analista).
4. Distingui sempre i fatti dalle dichiarazioni: "il Governo sostiene che…", "secondo l'ISTAT…".
5. Se le fonti si contraddicono, spiegalo in "divergenze".
6. Se è un'indiscrezione o non c'è conferma ufficiale, scrivilo chiaramente e metti "indiscrezione": true.
7. Se i materiali non bastano per una scheda affidabile, metti "materiale_insufficiente": true e lascia il resto vuoto.
8. Politica: tono equilibrato e non schierato; riporta le posizioni rilevanti delle parti e separa le dichiarazioni dai risultati verificabili.
9. Date: "data_evento" è la data del fatto (AAAA-MM-GG) se ricavabile dai materiali, altrimenti null.

STILE:
- Titolo chiaro, informativo e non sensazionalistico.
- "sintesi": 3-6 frasi. Cosa è successo, chi è coinvolto, quando, i dati principali e perché conta. Linguaggio colloquiale e preciso, niente burocratese.
- "perche_importa": solo i soggetti davvero toccati (famiglie, imprese, banche, investitori, conti pubblici, mercati, economia italiana, economia internazionale). Per ciascuno, "stato": "osservato" se l'effetto è già in corso secondo le fonti, "possibile" se è un effetto futuro.
- "spiegazione" (💡 Te lo spiego in parole semplici): inseriscila SOLO se la notizia contiene un concetto non immediato (spread, deficit, tassi BCE, dazi, OPA, CET1…). Qui puoi usare conoscenze generali per spiegare COME FUNZIONA il concetto, ma non per aggiungere fatti sulla notizia. Gli esempi numerici devono essere chiaramente ipotetici e iniziare con "Per esempio" o "Esempio:". Se non serve, null.
- "dati": cifre significative con etichetta, valore, periodo di riferimento e fonte. Il periodo deve essere quello indicato dalla fonte (mese, trimestre, anno, data della rilevazione); se la fonte non lo indica scrivi "periodo non indicato dalla fonte", mai la data dell'articolo al posto del periodo. Non mettere a confronto valori non omogenei.
- "contesto": breve, solo se serve per capire; non dare per scontato che il lettore ricordi i giorni precedenti. Anche il contesto deve venire dai materiali (fonti di oggi o schede precedenti): non aggiungere antefatti presi dalle tue conoscenze.
- "prossimi_passi": solo se ci sono sviluppi attesi nei materiali; "tipo" tra "ufficiale" (deciso), "programmato" (in calendario), "previsione" (di istituzioni o analisti, da attribuire), "ipotesi". Mai presentare una previsione come certa.
- Lunghezza proporzionata: notizie semplici brevi; decisioni BCE, manovre, crisi bancarie e riforme più approfondite.
- Niente morali finali, previsioni artificiose o frasi di riempimento.
- "termini": i concetti tecnici usati (massimo 4), con il nome comune (es. "spread", "deficit pubblico").
- Rispondi solo con JSON."""

CARD_SCHEMA = """{
  "titolo": "…",
  "sintesi": "…",
  "perche_importa": [{"per_chi": "famiglie", "testo": "…", "stato": "osservato|possibile", "fonti": ["S1"]}],
  "spiegazione": {"titolo": "Che cos'è …", "testo": "…"} oppure null,
  "dati": [{"etichetta": "…", "valore": "…", "periodo": "…", "fonte": "S1"}],
  "contesto": "…",
  "prossimi_passi": [{"tipo": "ufficiale|programmato|previsione|ipotesi", "testo": "…", "fonti": ["S2"]}],
  "affermazioni": [{"testo": "…", "fonti": ["S1"], "natura": "fatto|dichiarazione|interpretazione"}],
  "divergenze": "",
  "data_evento": "AAAA-MM-GG" oppure null,
  "termini": ["…"],
  "indiscrezione": false,
  "materiale_insufficiente": false
}"""


def card_user(category_name: str, materials: list[dict], previous: list[dict], today: str,
              errors: list[str] | None = None) -> str:
    parts = [f"OGGI È {today}. Categoria: {category_name}.\n\nMATERIALI DI OGGI:"]
    for m in materials:
        parts.append(
            f"[{m['ref']}] {m['source_name']} — «{m['title']}» — pubblicato {m['published'] or 'data non indicata'}"
            f" — {m['url']}\n{m['text']}")
    if previous:
        parts.append("\nSCHEDE GIÀ PUBBLICATE SULLO STESSO TEMA (solo contesto):")
        for p in previous:
            parts.append(f"[{p['ref']}] ({p['date']}) {p['title']}\n{p['summary']}")
    parts.append("\nSCHEMA DELLA RISPOSTA:\n" + CARD_SCHEMA)
    if errors:
        parts.append("\nLA VERSIONE PRECEDENTE È STATA RESPINTA DAI CONTROLLI PER QUESTI MOTIVI. "
                     "Correggi eliminando o riformulando ciò che non è supportato dai materiali:\n- " + "\n- ".join(errors))
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 3. Controllo di fedeltà
# ---------------------------------------------------------------------------
CHECK_SYSTEM = """Sei un verificatore (fact-checker) rigoroso. Confronti una scheda di notizia con i materiali da cui è stata scritta.
Segnala come problema ogni affermazione, numero, nome, data o attribuzione della scheda che NON è sostenuto dai materiali, che li travisa, che presenta come certo ciò che è ipotetico, o che attribuisce a una fonte qualcosa che quella fonte non dice.
Controlla con attenzione le parole che accompagnano i numeri e i tempi: se la fonte dice "300.000 tonnellate questo mese" e la scheda scrive "oltre 300.000 tonnellate subito", è un problema (quantità e tempi alterati).
La sezione "spiegazione" può contenere conoscenze generali su come funziona un concetto: segnalala solo se contiene fatti specifici sulla notizia non presenti nei materiali, o se contiene errori concettuali.
Non segnalare questioni di stile. Rispondi solo con JSON: {"fedele": true|false, "problemi": [{"campo": "…", "testo": "…", "motivo": "…"}]}"""


def check_user(materials: list[dict], previous: list[dict], card: dict) -> str:
    mat = "\n\n".join(f"[{m['ref']}] {m['source_name']} — «{m['title']}» ({m['published']})\n{m['text']}" for m in materials)
    prev = "\n".join(f"[{p['ref']}] {p['title']}: {p['summary']}" for p in previous)
    return (f"MATERIALI:\n{mat}\n\n" + (f"SCHEDE PRECEDENTI:\n{prev}\n\n" if prev else "") +
            "SCHEDA DA VERIFICARE:\n" + json.dumps(card, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------------------
# 4. Glossario
# ---------------------------------------------------------------------------
GLOSSARY_SYSTEM = """Scrivi voci di un glossario di economia, finanza, politica e tecnologia per un lettore non specialista, in italiano.
Ogni voce deve essere corretta, neutrale e senza riferimenti a fatti di cronaca specifici o a cifre attuali (che cambiano nel tempo).
Campi: "termine", "definizione_semplice" (1-2 frasi), "spiegazione" (3-5 frasi: come funziona, perché conta), "esempio" (concreto; se numerico, chiaramente ipotetico, iniziando con "Esempio illustrativo:"), "correlati" (altri termini).
Se un termine è ambiguo o non è un concetto da glossario, omettilo. Rispondi solo con JSON: {"voci": [...]}"""

REVIEW_SYSTEM = """Sei un docente di economia e finanza. Controlla la correttezza di voci di glossario scritte da altri.
Una voce è "corretta" solo se definizione, spiegazione ed esempio sono esatti e non fuorvianti, e se non contiene cifre attuali presentate come fatti.
Rispondi solo con JSON: {"esiti": [{"termine": "…", "corretta": true|false, "motivo": "…"}]}"""
