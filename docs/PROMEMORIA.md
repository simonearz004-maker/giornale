# Il Mio Giornale — promemoria personale

Tutto quello che serve per usare e gestire il giornale, in una pagina. Qui non ci sono password né chiavi segrete.

## Gli indirizzi

| Cosa | Dove |
|---|---|
| **Il giornale** (computer e telefono) | https://simonearz004-maker.github.io/giornale/ |
| Codice e aggiornamenti automatici (GitHub) | https://github.com/simonearz004-maker/giornale |
| Esecuzioni delle edizioni | https://github.com/simonearz004-maker/giornale/actions |
| Chiavi segrete (cassaforte GitHub) | https://github.com/simonearz004-maker/giornale/settings/secrets/actions |
| Database (Supabase) | https://supabase.com/dashboard/project/jaozdvopebzgwkuwzsgu |
| Chiave Gemini (Google AI Studio) | https://aistudio.google.com/api-keys |

**Accesso al giornale:** email simonearz004@gmail.com, con la password salvata nel gestore di password.

## Come funziona, in breve

- Ogni mattina, all'orario scelto nelle Impostazioni, parte l'edizione: raccoglie le notizie da 17 fonti, le fa scrivere a Gemini e le controlla. L'avvio puntuale lo dà Supabase, che ogni 10 minuti controlla l'orario e chiede a GitHub di partire (file `supabase/avvio-automatico.sql`); il pianificatore di GitHub resta come riserva. Se l'edizione non parte, il sistema riprova per 6 ore.
- Il token di GitHub usato da Supabase ha una scadenza: quando scade, creane uno nuovo (stessi permessi) e riesegui `avvio-automatico.sql` con il token nuovo.
- **Costo: 0 €.** GitHub, Supabase e il piano gratuito di Gemini non richiedono pagamenti.
- Ogni numero viene confrontato con le fonti e ogni scheda passa un secondo controllo. Le notizie che non lo superano vengono escluse e restano visibili in *Stato del sistema*.
- **Bollini di verifica:** *Fonte primaria* (documento ufficiale), *Confermata* (almeno due testate), *Fonte singola* (una sola testata), *Da confermare* (indiscrezione).

## Le cose che fai dal giornale

- **Impostazioni** (Altro → Impostazioni, o l'ingranaggio da computer): nome del giornale, orari (fino a 3 al giorno), sezioni da aggiungere, togliere o riordinare, argomenti da escludere, fonti, tema scuro e dimensione del testo.
- **Stato del sistema** (Altro → Stato del sistema): esito degli aggiornamenti, fonti che non rispondono, notizie escluse e perché.
- **Salvate, Cronologia, Glossario, Archivio, Cerca.**

## Domande all'IA sulle notizie

In fondo a ogni notizia (o con il pulsante **Chiedi**) puoi fare domande: l'IA risponde partendo dalla scheda e dalle fonti, citandole tra parentesi. Usa una **chiave Gemini separata** (secret `GEMINI_CHAT_KEY`, in un progetto Google diverso), quindi non toglie quota alle edizioni. Il numero massimo di domande al giorno si cambia nelle Impostazioni. Le risposte non passano i controlli delle schede: per i dati fa fede la fonte.

## Se serve un'edizione subito

GitHub → **Actions** → **Edizione quotidiana** → **Run workflow** → pulsante verde. Ci vogliono 10-30 minuti.

## Se qualcosa non va

| Cosa vedi | Cosa fare |
|---|---|
| "L'edizione di oggi non è ancora disponibile" dopo le 13 | Guarda *Stato del sistema*; poi rilancia a mano da Actions. GitHub ti avrà anche mandato un'email. |
| "Quota giornaliera esaurita" | Le quote gratuite di Gemini si azzerano ogni notte. Se succede spesso, lascia un solo orario o abbassa "Max notizie" nelle sezioni meno importanti. |
| Una fonte "Non risponde" da giorni | Disattivala dalle Impostazioni. |
| Supabase segnala il progetto "in pausa" | Nel pannello di Supabase premi *Restore*. Con il giornale attivo non dovrebbe succedere. |
| Altro | Apri una chat con Claude nel progetto "giornale digitale", descrivi il problema e allega uno screenshot. |

## Senza internet

L'aggiornamento avviene sui server di GitHub, quindi funziona anche a dispositivi spenti. Sul telefono, senza rete, puoi rileggere le notizie già aperte, con un avviso giallo che indica la data della copia. Prima di un viaggio apri il giornale, così l'edizione resta salvata.

## Riserva a pagamento (oggi spenta)

Se un giorno Gemini gratuito non bastasse, si può aggiungere Claude Haiku come riserva: è fatturato a consumo, separato dall'abbonamento a Claude, e costa circa 7-15 $ al mese solo nel caso peggiore. Si attiva aggiungendo il secret `ANTHROPIC_API_KEY` su GitHub e si spegne cancellandolo.

## I documenti

- **PROMEMORIA.md**: questa pagina.
- **README.md**: la guida completa di installazione e manutenzione.
- **ARCHITETTURA.md**: come è fatto il giornale dentro (per modifiche future).
- **database-giornale.sql**: il database iniziale. Serve solo per ricreare il giornale da zero, non va rieseguito.
- **giornale.zip**: copia completa del codice. Una copia identica è sempre su GitHub.
