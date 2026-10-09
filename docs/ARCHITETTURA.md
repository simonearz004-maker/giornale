# Il Mio Giornale — Progetto tecnico (Fase 2)

Documento di riferimento per capire come funziona il giornale e dove mettere le mani.

## 1. Architettura in breve

```
 ┌──────────────────────┐   ogni ora (controlla l'orario scelto)   ┌──────────────────────────┐
 │  GitHub Actions      │ ───────────────────────────────────────▶ │  Pipeline Python         │
 │  (pianificatore)     │                                          │  pipeline/giornale/      │
 └──────────────────────┘                                          └────────────┬─────────────┘
                                                                                │
        feed RSS (ANSA, BCE, Fed, ISTAT, Il Post, …) ──── raccolta ─────────────┤
        pagine degli articoli (solo se consentito) ─────── lettura ─────────────┤
        Gemini Flash (gratis) / Haiku (riserva, spenta) ── scrittura schede ────┤
                                                                                ▼
                                                                  ┌──────────────────────────┐
                                                                  │  Supabase (Postgres)     │
                                                                  │  notizie, fonti, glossario│
                                                                  │  preferenze, storico      │
                                                                  └────────────┬─────────────┘
                                                                               │ login + RLS
                                                                               ▼
                                                                  ┌──────────────────────────┐
                                                                  │  Sito PWA (GitHub Pages) │
                                                                  │  computer e smartphone   │
                                                                  └──────────────────────────┘
```

| Componente | Scelta | Perché | Costo |
|---|---|---|---|
| Pianificatore | GitHub Actions (cron orario + controllo orario) | Gira anche a sito chiuso; gratuito su repository pubblico | 0 € |
| Pipeline | Python 3.12 | Librerie mature per RSS ed estrazione testo | 0 € |
| Modello | Gemini Flash (piano gratuito), con catena di modelli di riserva gratuiti; Claude Haiku predisposto ma spento | Richiesta di costo zero | 0 € |
| Database | Supabase Postgres + Auth | SQL vero, login, permessi per riga (RLS); la scrittura quotidiana evita la pausa per inattività | 0 € |
| Sito | Vite + JavaScript, PWA | Leggero, nessun server da mantenere, installabile sul telefono | 0 € |
| Hosting | GitHub Pages (`tuonome.github.io/giornale`) | Stesso account di GitHub, HTTPS incluso | 0 € |

**Privacy dei contenuti.** Il codice è pubblico, i contenuti no: le notizie stanno nel database, leggibile solo dal tuo account (Row Level Security). Nessuna chiave segreta è nel codice: la chiave di servizio Supabase e quella di Gemini stanno nei *Secrets* di GitHub. La chiave "anon" di Supabase nel sito è pubblica per progettazione e da sola non dà accesso a nulla.

## 2. Database

| Tabella | Contenuto |
|---|---|
| `settings` | Riga unica: nome del giornale, orari di aggiornamento, argomenti esclusi, numero di "notizie da non perdere", email del proprietario, preferenze di visualizzazione |
| `categories` | Categorie modificabili: nome, sotto-argomenti, parole chiave, priorità (1–5), max notizie, attiva/disattiva, in homepage, personalizzata |
| `sources` | Feed RSS: nome, URL, tipo (`primaria` o `testata`), attivo, accesso al testo completo consentito, stato dell'ultimo controllo |
| `runs` | Registro di ogni esecuzione: esito, modello usato, numeri, errori |
| `editions` | Un'edizione per giorno: data, ora di pubblicazione e ultimo aggiornamento, note (es. categorie senza notizie) |
| `stories` | Le schede: titolo, sintesi, perché è importante, spiegazione, dati, contesto, prossimi passi, livello di verifica, rilevanza, filo narrativo (`thread_id`) per le notizie in evoluzione |
| `story_sources` | Le fonti di ciascuna scheda con titolo, data e link |
| `glossary` + `glossary_story_links` | Voci del glossario e collegamenti alle notizie |
| `user_story_state` | Notizie salvate e già lette |

## 3. Flusso della pipeline

1. **Controllo orario** — parte solo all'ora scelta nelle impostazioni (fuso Europe/Rome) e una sola volta per fascia oraria.
2. **Raccolta** — scarica i feed attivi, registra lo stato di ogni fonte, scarta le voci senza data o più vecchie della finestra (dall'ultima edizione, max 36 ore).
3. **Esclusioni** — scarta le voci che contengono argomenti esclusi.
4. **Deduplica e raggruppamento** — stesso URL, oppure titoli molto simili, vanno nello stesso gruppo.
5. **Selezione (1 richiesta al modello)** — il modello riceve i titoli dei gruppi e le categorie attive: unisce i gruppi che parlano dello stesso fatto, assegna categoria e rilevanza secondo un criterio esplicito (impatto economico e politico, non popolarità), segnala i seguiti di notizie dei giorni precedenti.
6. **Lettura delle fonti** — per ogni fatto scelto legge il testo degli articoli, solo dove `robots.txt` lo consente e non c'è paywall; altrimenti usa il sommario del feed.
7. **Scrittura della scheda (1 richiesta per notizia)** — il modello scrive solo a partire dai materiali numerati [S1], [S2]…, cita la fonte di ogni affermazione e di ogni dato.
8. **Controlli automatici** (codice, non modello):
   - ogni numero di titolo, sintesi, dati, contesto e prossimi passi deve comparire nel testo delle fonti;
   - ogni affermazione deve citare una fonte esistente;
   - le date devono essere coerenti, e le notizie vecchie vengono scartate;
   - niente duplicati con le schede già pubblicate.

   Se un controllo fallisce, la scheda viene riscritta una volta con l'elenco degli errori. Se fallisce ancora, viene esclusa e annotata nel registro.
9. **Controllo di fedeltà (1 richiesta per notizia)** — un secondo passaggio confronta la scheda con le fonti e segnala affermazioni non supportate; le schede con problemi vengono escluse.
10. **Livello di verifica**, calcolato con regole e non inventato dal modello:
    - **Fonte primaria**: almeno una fonte istituzionale citata;
    - **Confermata**: due o più testate indipendenti;
    - **Fonte singola**;
    - **Non confermata**: indiscrezioni, mostrate in una sezione separata.
11. **Glossario** — i termini nuovi vengono definiti, ricontrollati da un secondo passaggio e collegati alle notizie.
12. **Salvataggio** — edizione, schede, fonti, collegamenti, esito dell'esecuzione.

**Budget di richieste.** C'è un tetto di richieste per esecuzione (predefinito 60). Se le richieste disponibili non bastano, il sistema pubblica meno notizie, mai notizie meno controllate. Se le quote gratuite finiscono a metà, salva quello che è già passato dai controlli e registra l'esito come "parziale".

## 4. Pagine del sito

- **Home**: testata, data, ultimo aggiornamento, avvisi di stato, "Le notizie da non perdere", sezioni per categoria in ordine di priorità, "Concetti di oggi", notizie da confermare.
- **Categoria**: notizie della sezione, con filtro per data.
- **Notizia**: si apre come pannello sopra la pagina corrente (non si perde il punto) oppure come pagina da link condiviso.
- **Glossario**: ricerca, voce completa, notizie collegate.
- **Archivio**: elenco delle edizioni e singola edizione passata.
- **Cerca**: parole chiave, con filtri per categoria e data.
- **Salvate**, **Cronologia letture**.
- **Impostazioni**: categorie, orari, esclusioni, fonti, nome, tema, dimensione testo.

**Smartphone.** Barra di navigazione in basso, testo leggibile senza zoom (corpo minimo 17 px), pulsanti di almeno 44 px, installabile come app. Offline mostra l'ultima edizione scaricata con la data in evidenza.

## 5. Limiti dichiarati della prima versione

- La lingua dei contenuti è solo l'italiano.
- I feed di Banca d'Italia ed Eurostat non sono usati perché le loro regole vietano l'accesso automatico; le loro notizie arrivano tramite le testate.
- Il piano gratuito di Gemini ha quote decise da Google e non garantite.
- Gli orari di GitHub Actions possono slittare di qualche minuto nelle ore di punta.
