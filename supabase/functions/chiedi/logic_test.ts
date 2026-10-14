// Test della funzione "chiedi" con database e Gemini finti. Avvio: deno test supabase/functions/chiedi/
import { answerQuestion, buildPrompt, geminiGenerate, HttpError, startOfTodayRome, type Db, type Generate, type Story } from "./logic.ts";

function assert(cond: unknown, msg = "asserzione fallita") {
  if (!cond) throw new Error(msg);
}
async function rejects(p: Promise<unknown>, status: number, text?: string) {
  try {
    await p;
  } catch (e) {
    assert(e instanceof HttpError, `atteso HttpError, ottenuto ${e}`);
    assert((e as HttpError).status === status, `stato ${(e as HttpError).status} invece di ${status}: ${(e as Error).message}`);
    if (text) assert((e as Error).message.includes(text), `messaggio: ${(e as Error).message}`);
    return;
  }
  throw new Error("doveva fallire");
}

const ID = "11111111-2222-4333-8444-555555555555";
const STORY: Story = {
  id: ID, title: "La Bce lascia i tassi fermi", summary: "Il tasso sui depositi resta al 2,00%.", edition_date: "2026-10-13",
  event_date: "2026-10-13", context: "", why_important: [], explainer: null,
  data_points: [{ etichetta: "Tasso sui depositi", valore: "2,00%", periodo: "da oggi", fonte: "S1" }],
  next_steps: [], claims: [{ testo: "Tassi fermi", fonti: ["S1"], natura: "fatto" }], divergences: "", verification_level: "fonte_primaria",
  story_sources: [{ ref: "S1", source_name: "BCE", title: "Decisioni di politica monetaria", url: "https://www.ecb.europa.eu/x",
    published_at: "2026-10-13T12:15:00Z", excerpt: "Il Consiglio direttivo ha deciso di lasciare invariati i tre tassi." }],
};

function fakeDb(opts: { owner?: boolean; used?: number; limit?: number } = {}) {
  const saved: { question: string; answer: string; model: string }[] = [];
  const db: Db = {
    ownerSettings: async () => (opts.owner === false ? null : { max_questions_per_day: opts.limit ?? 30 }),
    countQuestionsSince: async () => opts.used ?? 0,
    story: async (id) => (id === ID ? STORY : null),
    history: async () => saved.map((s) => ({ question: s.question, answer: s.answer })),
    saveQuestion: async (r) => void saved.push(r),
  };
  return { db, saved };
}
const okGen: Generate = async (model) => ({ ok: true, text: `Risposta da ${model} [S1]` });

Deno.test("risposta, salvataggio e domande rimaste", async () => {
  const { db, saved } = fakeDb({ used: 3, limit: 30 });
  const r = await answerQuestion({ story_id: ID, question: "  Cosa  cambia per i mutui? " }, db, okGen, ["m1"]);
  assert(r.answer === "Risposta da m1 [S1]" && r.remaining === 26 && r.limit === 30);
  assert(saved.length === 1 && saved[0].question === "Cosa cambia per i mutui?");
});

Deno.test("non proprietario, limite giornaliero, input non validi", async () => {
  await rejects(answerQuestion({ story_id: ID, question: "ciao" }, fakeDb({ owner: false }).db, okGen), 403);
  await rejects(answerQuestion({ story_id: ID, question: "ciao" }, fakeDb({ used: 30, limit: 30 }).db, okGen), 429, "30 domande");
  await rejects(answerQuestion({ story_id: "x", question: "ciao" }, fakeDb().db, okGen), 400);
  await rejects(answerQuestion({ story_id: ID, question: "" }, fakeDb().db, okGen), 400);
  await rejects(answerQuestion({ story_id: ID, question: "a".repeat(601) }, fakeDb().db, okGen), 400);
  await rejects(answerQuestion({ story_id: "99999999-2222-4333-8444-555555555555", question: "ciao" }, fakeDb().db, okGen), 404);
});

Deno.test("passaggio al modello successivo e quota finita", async () => {
  const tried: string[] = [];
  const gen: Generate = async (m) => {
    tried.push(m);
    return m === "m3" ? { ok: true, text: "ok" } : { ok: false, kind: "quota", detail: "quota esaurita (429)" };
  };
  const r = await answerQuestion({ story_id: ID, question: "perché?" }, fakeDb().db, gen, ["m1", "m2", "m3"]);
  assert(r.model === "m3" && tried.join() === "m1,m2,m3");
  const { db, saved } = fakeDb();
  await rejects(answerQuestion({ story_id: ID, question: "perché?" }, db,
    async () => ({ ok: false, kind: "quota", detail: "quota esaurita (429)" }), ["m1", "m2"]), 429, "quota gratuita");
  assert(saved.length === 0, "le domande fallite non contano nel limite");
});

Deno.test("il prompt contiene scheda, fonti con estratto e storico", () => {
  const p = buildPrompt(STORY, [{ question: "Q1", answer: "A1" }], "E per i mutui?");
  for (const s of ["La Bce lascia i tassi fermi", "[S1] BCE", "lasciare invariati", "D: Q1", "DOMANDA DEL LETTORE: E per i mutui?", "2,00%"]) {
    assert(p.includes(s), `manca: ${s}`);
  }
  const noExcerpt = buildPrompt({ ...STORY, story_sources: [{ ...STORY.story_sources[0], excerpt: null }] }, [], "x");
  assert(noExcerpt.includes("testo non disponibile"));
});

Deno.test("mezzanotte italiana in UTC (ora legale e solare)", () => {
  assert(startOfTodayRome(new Date("2026-10-13T07:40:00Z")) === "2026-10-12T22:00:00.000Z");
  assert(startOfTodayRome(new Date("2026-12-01T10:00:00Z")) === "2026-11-30T23:00:00.000Z");
  assert(startOfTodayRome(new Date("2026-10-12T23:30:00Z")) === "2026-10-12T22:00:00.000Z"); // 01:30 del 13 a Roma
});

Deno.test("modelli sovraccarichi o lenti: si passa al successivo", async () => {
  const slow = (async (_u: string, init: RequestInit) => {
    await new Promise((resolve, reject) => {
      const t = setTimeout(resolve, 5000);
      init.signal?.addEventListener("abort", () => { clearTimeout(t); reject(init.signal!.reason); });
    });
    return new Response("{}");
  }) as unknown as typeof fetch;
  const r = await geminiGenerate("k", slow, "http://x", 50)("m", "s", "u");
  assert(!r.ok && r.kind === "unavailable" && /30 secondi/.test(r.detail));
  const busy: Generate = async () => ({ ok: false, kind: "unavailable", detail: "modello sovraccarico o non disponibile (503)" });
  await rejects(answerQuestion({ story_id: ID, question: "perché?" }, fakeDb().db, busy, ["m1", "m2"]), 503, "sovraccarichi");
});

Deno.test("Gemini: testo, quota, modello inesistente", async () => {
  const fake = (status: number, body: unknown) => (async () => new Response(typeof body === "string" ? body : JSON.stringify(body), { status })) as unknown as typeof fetch;
  const ok = await geminiGenerate("k", fake(200, { candidates: [{ content: { parts: [{ text: "pensiero", thought: true }, { text: "Ciao" }] } }] }))("m", "s", "u");
  assert(ok.ok && ok.text === "Ciao");
  const q = await geminiGenerate("k", fake(429, "{}"))("m", "s", "u");
  assert(!q.ok && q.kind === "quota");
  const nf = await geminiGenerate("k", fake(404, "model not found"))("m", "s", "u");
  assert(!nf.ok && nf.kind === "unavailable");
});
