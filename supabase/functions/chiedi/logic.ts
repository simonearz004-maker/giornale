// Domande all'IA su una notizia: logica separata dal server, così si può provare con dati finti.
//
// Regole:
// - risponde solo il proprietario del giornale (le letture passano dalle regole di sicurezza del database);
// - si parte dalla scheda e dagli estratti delle fonti di quella notizia;
// - tetto di domande al giorno (Impostazioni del giornale);
// - usa una chiave Gemini separata (GEMINI_CHAT_KEY), così le domande non consumano la quota delle edizioni.

export const DEFAULT_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"];

export interface Db {
  ownerSettings(): Promise<{ max_questions_per_day: number } | null>;
  countQuestionsSince(isoUtc: string): Promise<number>;
  story(id: string): Promise<Story | null>;
  history(storyId: string, limit: number): Promise<{ question: string; answer: string }[]>;
  saveQuestion(row: { story_id: string; question: string; answer: string; model: string }): Promise<void>;
}

export interface Story {
  id: string;
  title: string;
  summary: string;
  edition_date: string;
  event_date: string | null;
  context: string;
  why_important: { chi: string; testo: string; stato: string }[];
  explainer: { titolo: string; testo: string } | null;
  data_points: { etichetta: string; valore: string; periodo: string; fonte: string }[];
  next_steps: { tipo: string; testo: string }[];
  claims: { testo: string; fonti: string[]; natura: string }[];
  divergences: string;
  verification_level: string;
  story_sources: { ref: string; source_name: string; title: string; url: string; published_at: string | null; excerpt?: string | null }[];
}

export type Generate = (model: string, system: string, user: string) => Promise<GenResult>;
export type GenResult = { ok: true; text: string } | { ok: false; kind: "quota" | "unavailable" | "error"; detail: string };

export class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export const SYSTEM = `Sei l'assistente di un quotidiano personale in italiano. Il lettore ha appena letto una notizia e ti fa una domanda.

Regole:
1. Per i fatti della notizia (chi, cosa, quando, quanto) usa SOLO la scheda e gli estratti delle fonti forniti. Cita la fonte tra parentesi quadre, es. [S1], subito dopo il fatto.
2. Puoi usare conoscenze generali solo per spiegare concetti (come funziona lo spread, cos'è un dazio, come i tassi influenzano i mutui). In quel caso scrivi "In generale," e non attribuire a quella spiegazione fatti specifici sulla notizia.
3. Se la risposta non è nei materiali scrivi chiaramente "Le fonti di questa notizia non lo dicono" e, se utile, suggerisci cosa cercare. Non inventare mai cifre, date, nomi o dichiarazioni.
4. Non conosci gli sviluppi successivi alla data della notizia: se la domanda riguarda il "dopo", dillo.
5. Non dare consigli di investimento personalizzati: puoi spiegare i possibili effetti in generale.
6. Politica: tono equilibrato, distingui fatti, dichiarazioni e interpretazioni.
7. Stile: italiano colloquiale e chiaro, come una persona competente davanti a un caffè. Di norma 3-8 frasi; più lungo solo se la domanda lo richiede. Niente titoli, niente elenchi lunghi, niente formattazione markdown tranne a capo tra i paragrafi.`;

export function buildPrompt(s: Story, history: { question: string; answer: string }[], question: string): string {
  const parts: string[] = [];
  parts.push(`NOTIZIA (edizione del ${s.edition_date}${s.event_date ? `, fatto del ${s.event_date}` : ""}): ${s.title}`);
  parts.push(`Sintesi: ${s.summary}`);
  if (s.why_important?.length) parts.push("Perché è importante:\n" + s.why_important.map((i) => `- ${i.chi} (${i.stato}): ${i.testo}`).join("\n"));
  if (s.data_points?.length) parts.push("Dati:\n" + s.data_points.map((d) => `- ${d.etichetta}: ${d.valore} (${d.periodo}) [${d.fonte}]`).join("\n"));
  if (s.context) parts.push(`Contesto: ${s.context}`);
  if (s.next_steps?.length) parts.push("Prossimi passi:\n" + s.next_steps.map((p) => `- (${p.tipo}) ${p.testo}`).join("\n"));
  if (s.claims?.length) parts.push("Affermazioni verificate:\n" + s.claims.map((c) => `- ${c.testo} [${(c.fonti || []).join(", ")}] (${c.natura})`).join("\n"));
  if (s.divergences) parts.push(`Divergenze tra le fonti: ${s.divergences}`);
  if (s.explainer?.testo) parts.push(`Spiegazione già data al lettore: ${s.explainer.titolo}. ${s.explainer.testo}`);
  parts.push("FONTI:");
  for (const src of s.story_sources || []) {
    const when = src.published_at ? src.published_at.slice(0, 10) : "data non indicata";
    const text = (src.excerpt || "").trim();
    parts.push(`[${src.ref}] ${src.source_name} — «${src.title}» (${when})\n${text ? text.slice(0, 6000) : "(testo non disponibile: usa solo la scheda)"}`);
  }
  if (history.length) {
    parts.push("DOMANDE GIÀ FATTE SU QUESTA NOTIZIA:\n" + history.map((h) => `D: ${h.question}\nR: ${h.answer}`).join("\n\n"));
  }
  parts.push(`DOMANDA DEL LETTORE: ${question}`);
  return parts.join("\n\n");
}

/** Mezzanotte di oggi (ora italiana) espressa in UTC. */
export function startOfTodayRome(now: Date = new Date()): string {
  const fmt = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome", year: "numeric", month: "2-digit", day: "2-digit" });
  const day = fmt.format(now); // AAAA-MM-GG
  const off = new Intl.DateTimeFormat("en-US", { timeZone: "Europe/Rome", timeZoneName: "shortOffset" })
    .formatToParts(now).find((p) => p.type === "timeZoneName")?.value || "GMT+1"; // es. "GMT+2"
  const m = off.match(/GMT([+-])(\d{1,2})(?::(\d{2}))?/);
  const sign = m && m[1] === "-" ? -1 : 1;
  const hours = m ? Number(m[2]) : 1;
  const mins = m && m[3] ? Number(m[3]) : 0;
  const utc = new Date(`${day}T00:00:00Z`).getTime() - sign * (hours * 60 + mins) * 60000;
  return new Date(utc).toISOString();
}

export interface Result {
  answer: string;
  model: string;
  remaining: number;
  limit: number;
}

export async function answerQuestion(
  input: { story_id?: unknown; question?: unknown },
  db: Db,
  generate: Generate,
  models: string[] = DEFAULT_MODELS,
  now: Date = new Date(),
): Promise<Result> {
  const storyId = typeof input.story_id === "string" ? input.story_id.trim() : "";
  const question = typeof input.question === "string" ? input.question.trim().replace(/\s+/g, " ") : "";
  if (!/^[0-9a-f-]{36}$/i.test(storyId)) throw new HttpError(400, "Notizia non valida.");
  if (question.length < 2) throw new HttpError(400, "Scrivi una domanda.");
  if (question.length > 600) throw new HttpError(400, "La domanda è troppo lunga (massimo 600 caratteri).");

  const settings = await db.ownerSettings();
  if (!settings) throw new HttpError(403, "Accesso non autorizzato.");
  const limit = Number(settings.max_questions_per_day ?? 30);
  const used = await db.countQuestionsSince(startOfTodayRome(now));
  if (limit <= 0) throw new HttpError(403, "Le domande sono disattivate nelle Impostazioni.");
  if (used >= limit) throw new HttpError(429, `Hai usato tutte le ${limit} domande di oggi. Il conteggio riparte domani.`);

  const story = await db.story(storyId);
  if (!story) throw new HttpError(404, "Notizia non trovata.");
  const history = await db.history(storyId, 6);
  const prompt = buildPrompt(story, history, question);

  const notes: string[] = [];
  for (const model of models) {
    const r = await generate(model, SYSTEM, prompt);
    if (r.ok) {
      const answer = r.text.trim();
      if (!answer) {
        notes.push(`${model}: risposta vuota`);
        continue;
      }
      await db.saveQuestion({ story_id: storyId, question, answer, model });
      return { answer, model, remaining: Math.max(0, limit - used - 1), limit };
    }
    notes.push(`${model}: ${r.detail}`);
    if (r.kind === "error") break; // errore non legato alla quota: inutile insistere con altri modelli
  }
  const allQuota = notes.length > 0 && notes.every((n) => /quota|429/i.test(n));
  if (allQuota) throw new HttpError(429, "La quota gratuita di Gemini per le domande è finita per oggi. Riprova dopo le 9:00.");
  const allBusy = notes.length > 0 && notes.every((n) => /sovraccarico|entro 30 secondi|non disponibile/i.test(n));
  if (allBusy) throw new HttpError(503, "I modelli di Gemini sono sovraccarichi in questo momento. Riprova tra qualche minuto.");
  throw new HttpError(502, "L'IA non ha risposto. Riprova tra poco. (" + notes.join("; ").slice(0, 300) + ")");
}

/** Chiamata reale a Gemini. */
export function geminiGenerate(apiKey: string, fetchImpl: typeof fetch = fetch,
  base = "https://generativelanguage.googleapis.com", timeoutMs = 30000): Generate {
  return async (model, system, user) => {
    let res: Response;
    try {
      res = await fetchImpl(`${base}/v1beta/models/${model}:generateContent`, {
        // un modello sovraccarico non deve bloccare la risposta: dopo 30 secondi si passa al successivo
        signal: AbortSignal.timeout(timeoutMs),
        method: "POST",
        headers: { "Content-Type": "application/json", "x-goog-api-key": apiKey },
        body: JSON.stringify({
          systemInstruction: { parts: [{ text: system }] },
          contents: [{ role: "user", parts: [{ text: user }] }],
          // margine ampio: nei modelli che "ragionano" il ragionamento consuma parte dei token
          generationConfig: { temperature: 0.3, maxOutputTokens: 4096 },
        }),
      });
    } catch (e) {
      const timedOut = e instanceof DOMException && (e.name === "TimeoutError" || e.name === "AbortError");
      return { ok: false, kind: "unavailable", detail: timedOut ? "nessuna risposta entro 30 secondi" : `rete: ${String(e).slice(0, 120)}` };
    }
    const body = await res.text();
    if (res.status === 200) {
      try {
        const data = JSON.parse(body);
        const parts = data?.candidates?.[0]?.content?.parts || [];
        const text = parts.filter((p: { thought?: boolean }) => !p.thought).map((p: { text?: string }) => p.text || "").join("");
        return { ok: true, text };
      } catch {
        return { ok: false, kind: "error", detail: "risposta non leggibile" };
      }
    }
    if (res.status === 429) return { ok: false, kind: "quota", detail: "quota esaurita (429)" };
    if ([400, 403, 404].includes(res.status) && /not found|not supported|permission/i.test(body)) {
      return { ok: false, kind: "unavailable", detail: `modello non disponibile (${res.status})` };
    }
    if (res.status >= 500) return { ok: false, kind: "unavailable", detail: `modello sovraccarico o non disponibile (${res.status})` };
    return { ok: false, kind: "error", detail: `HTTP ${res.status}: ${body.slice(0, 150)}` };
  };
}
