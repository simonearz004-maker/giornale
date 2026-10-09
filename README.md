# Il Mio Giornale

Quotidiano digitale personale di economia, finanza, imprese e politica. Ogni mattina raccoglie le notizie da fonti verificabili, le seleziona secondo le tue preferenze, le spiega in parole semplici e le pubblica su un sito che leggi dal computer o dal telefono.

- **Costo:** 0 €. GitHub, Supabase e il piano gratuito di Gemini non richiedono pagamenti.
- **Aggiornamento:** automatico, agli orari che scegli nelle Impostazioni, anche a sito chiuso.
- **Verifica:** ogni numero confrontato con le fonti, controllo di fedeltà, livello di verifica calcolato con regole e fonti sempre cliccabili.

Come funziona dentro: [docs/ARCHITETTURA.md](docs/ARCHITETTURA.md).

```
pipeline/   programma Python che ogni giorno raccoglie, verifica e salva le notizie
web/        il sito (PWA installabile sul telefono)
supabase/   struttura del database (schema.sql) e dati iniziali (seed.sql)
.github/    automatismi: edizione quotidiana, pubblicazione del sito, test, manutenzione
docs/       documentazione tecnica
```

---

## Pubblicazione: la prima volta (circa 30-40 minuti)

Ti servono tre account gratuiti: **GitHub**, **Supabase** e **Google AI Studio**. Nessuno chiede la carta di credito.

### 1. GitHub
1. Crea un account su [github.com](https://github.com/signup).
2. Crea un repository **pubblico** chiamato `giornale`: pulsante **New** → nome `giornale` → *Public* → **Create repository**.
   Pubblico è necessario perché GitHub Pages e GitHub Actions siano gratuiti senza limiti. Il codice è visibile, le notizie no: stanno nel database protetto, e nel codice non c'è alcuna chiave segreta.
3. Carica il progetto nel repository. Lo carico io se colleghi GitHub a Claude; in alternativa trascina i file nella pagina del repository (**Add file → Upload files**).

### 2. Supabase (database e accesso)
1. Crea un account su [supabase.com](https://supabase.com), anche con il tuo account GitHub.
2. **New project**: nome `giornale`, scegli una password per il database e conservala, regione **Central EU (Frankfurt)**, piano **Free**.
3. Apri **SQL Editor → New query**, incolla tutto il contenuto di `supabase/schema.sql` e premi **Run**.
4. Nuova query: incolla `supabase/seed.sql` e, **prima di eseguirlo**, sostituisci `LA_TUA_EMAIL` con l'email che userai per accedere al giornale. Poi **Run**.
5. **Authentication → Users → Add user → Create new user**: inserisci la stessa email e una password; spunta *Auto Confirm User*.
6. Nelle impostazioni di Authentication (sezione *Sign In / Providers*) disattiva **Allow new users to sign up**: così nessun altro può registrarsi. Anche se qualcuno ci riuscisse, non vedrebbe nulla: il database mostra i contenuti solo all'email del proprietario.
7. **Project Settings → API Keys**: annota tre valori.
   - Project URL (anche dal pulsante **Connect**): `https://xxxx.supabase.co`
   - **Publishable key** (`sb_publishable_…`): va nel sito, è pubblica per progettazione.
   - **Secret key** (`sb_secret_…`): **segreta**, solo nei Secrets di GitHub, mai altrove.

   Se vedi le chiavi "legacy", `anon` corrisponde alla publishable e `service_role` alla secret.

### 3. Gemini (la scrittura delle schede, gratis)
1. Vai su [aistudio.google.com](https://aistudio.google.com) con un account Google.
2. **Get API key → Create API key**. Annotala: è segreta.

Nota: sul piano gratuito Google può usare i testi inviati per migliorare i suoi prodotti. Qui si inviano solo notizie pubbliche, nessun dato personale.

### 4. Collegare tutto (Secrets di GitHub)
Nel repository: **Settings → Secrets and variables → Actions → New repository secret**. Crea questi quattro:

| Nome | Valore |
|---|---|
| `SUPABASE_URL` | il Project URL |
| `SUPABASE_SERVICE_KEY` | la Secret key di Supabase |
| `SUPABASE_ANON_KEY` | la Publishable key di Supabase |
| `GEMINI_API_KEY` | la chiave di Google AI Studio |

### 5. Accendere il sito e l'aggiornamento
1. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. Scheda **Actions**: se richiesto, abilita i workflow.
3. Esegui **Pubblica il sito → Run workflow**. Dopo un paio di minuti il sito è su `https://TUONOME.github.io/giornale/`.
4. Esegui **Edizione quotidiana → Run workflow** (lascia spuntato *Pubblica subito*). La prima edizione richiede circa 10-15 minuti.
5. Apri il sito e accedi con email e password del passo 2.5.

Da qui in poi l'edizione esce da sola ogni giorno all'orario scelto (predefinito: 07:00).

### 6. Sul telefono
- **iPhone (Safari):** apri il sito → Condividi → **Aggiungi alla schermata Home**.
- **Android (Chrome):** apri il sito → menu ⋮ → **Installa app** o **Aggiungi a schermata Home**.

Si apre come un'app. Le ultime notizie consultate restano leggibili anche senza rete, con la data ben visibile.

---

## Uso quotidiano

- **Impostazioni** (icona ingranaggio, o Altro → Impostazioni): nome del giornale, orari (fino a 3 al giorno), sezioni (aggiungi, togli, priorità, numero di notizie, homepage), argomenti da escludere, fonti (attiva, preferita, aggiungi un feed RSS), tema e dimensione del testo.
- **Stato del sistema** (Altro → Stato del sistema): esito di ogni aggiornamento, fonti che non rispondono e **notizie escluse dai controlli, con il motivo**.
- **Pubblicare subito** un'edizione fuori orario: GitHub → Actions → Edizione quotidiana → Run workflow.

## Se qualcosa non va

| Cosa vedi | Cosa fare |
|---|---|
| "L'edizione di oggi non è ancora disponibile" | Apri Stato del sistema. Se l'ultima esecuzione è fallita, GitHub ti ha anche mandato un'email con il dettaglio. Puoi rilanciare a mano da Actions. |
| "Quota giornaliera esaurita" nello stato | Le quote gratuite di Gemini si azzerano a mezzanotte (ora del Pacifico). Riduci gli orari a uno o abbassa *max notizie* delle sezioni meno importanti. |
| Un modello Gemini viene segnalato come non disponibile | Google cambia i nomi dei modelli: crea la variabile `GEMINI_MODELS` (Settings → Secrets and variables → Actions → Variables) con l'elenco dei modelli Flash gratuiti attuali, separati da virgole. |
| Una fonte "Non risponde" da giorni | Disattivala dalle Impostazioni o sostituiscila con un altro feed. |
| Il sito chiede l'accesso ma poi dà errore | L'email in `settings.owner_email` (Supabase → Table Editor → settings) deve essere identica a quella con cui accedi. |
| Supabase segnala il progetto in pausa | Succede dopo 7 giorni senza attività. Con il giornale attivo non dovrebbe accadere; se succede, premi *Restore* nel pannello di Supabase. |

## Attivare la riserva a pagamento (facoltativo)

Se un giorno Gemini gratuito non bastasse più, puoi aggiungere Claude Haiku come riserva: entra in gioco solo quando Gemini rifiuta le richieste.

1. Crea una chiave su [console.anthropic.com](https://console.anthropic.com) e imposta un tetto di spesa.
2. Aggiungila ai Secrets di GitHub come `ANTHROPIC_API_KEY`.

È fatturata a consumo, a parte rispetto all'abbonamento a Claude. Il costo stimato è sui 7–15 $ al mese **solo** nel caso peggiore in cui faccia tutto il lavoro. Per spegnerla basta cancellare il secret.

## Manutenzione

- **Modificare il progetto:** ogni modifica caricata su GitHub ripubblica il sito da sola (workflow *Pubblica il sito*) e passa dai test (workflow *Test*).
- **Attività del repository:** GitHub sospende i job pianificati dei repository pubblici dopo 60 giorni di inattività. Il workflow *Manutenzione* registra un controllo ogni lunedì e lo evita; non serve fare nulla.
- **Copia del database:** il piano gratuito di Supabase non fa backup automatici. Per una copia: Supabase → Table Editor → tabella → **Export to CSV** (almeno `stories`, `story_sources`, `glossary`).
- **Dati iniziali:** categorie, fonti e glossario di base sono in `pipeline/giornale/seed_data.py`. Dopo una modifica: `cd pipeline && python -m giornale.genera_seed`. Il file `seed.sql` non sovrascrive ciò che esiste già.
- **Istruzioni al modello** (stile e regole delle schede): `pipeline/giornale/prompts.py`.

## Sviluppo e test

```bash
# Pipeline
cd pipeline && pip install -r requirements.txt && python -m pytest -q

# Sito in locale (serve un progetto Supabase, anche di prova)
cd web && npm install
VITE_SUPABASE_URL=… VITE_SUPABASE_ANON_KEY=… npm run dev
```

`web/e2e/` contiene il test completo nel browser (47 controlli), da eseguire contro una replica locale di Supabase: PostgreSQL con `schema.sql` e `seed.sql`, PostgREST e `fake_supabase.py`. I dati di prova (`seed_ui.py`) sono fittizi e marcati «[Prova]».

## Limiti noti

- I contenuti sono solo in italiano.
- Banca d'Italia ed Eurostat vietano l'accesso automatico ai loro feed: le loro notizie arrivano tramite le testate.
- Per le fonti con abbonamento (Sole 24 Ore, Repubblica) si usano solo titolo e sommario del feed, mai il testo dietro il paywall.
- Le quote gratuite di Gemini sono decise da Google e possono cambiare. In quel caso il giornale pubblica meno notizie o salta un'edizione, ma non pubblica schede non verificate.
- Gli orari di GitHub Actions possono slittare di qualche minuto. Se un'esecuzione salta, la pipeline recupera nelle 6 ore successive.
