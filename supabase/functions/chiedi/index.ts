// Edge Function "chiedi": risponde alle domande del proprietario su una notizia.
// Deploy automatico da GitHub (workflow "Funzioni Supabase").
import { createClient } from "npm:@supabase/supabase-js@2.117.3";
import { answerQuestion, DEFAULT_MODELS, geminiGenerate, HttpError, type Db, type Story } from "./logic.ts";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json(405, { error: "Metodo non consentito." });

  const auth = req.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return json(401, { error: "Accesso richiesto." });
  const geminiKey = Deno.env.get("GEMINI_CHAT_KEY");
  if (!geminiKey) return json(503, { error: "Le domande non sono ancora attive: manca la chiave GEMINI_CHAT_KEY." });

  const url = Deno.env.get("SUPABASE_URL")!;
  const publicKey = Deno.env.get("SUPABASE_ANON_KEY") || req.headers.get("apikey") || "";
  // Tutte le letture e scritture avvengono con l'identità dell'utente: valgono le regole di sicurezza del database.
  const sb = createClient(url, publicKey, { global: { headers: { Authorization: auth } }, auth: { persistSession: false } });
  const { data: who, error: authErr } = await sb.auth.getUser(auth.slice(7));
  if (authErr || !who?.user) return json(401, { error: "Sessione scaduta: esci e rientra nel giornale." });

  const db: Db = {
    async ownerSettings() {
      const { data } = await sb.from("settings").select("max_questions_per_day").eq("id", 1).maybeSingle();
      return data;
    },
    async countQuestionsSince(iso) {
      const { count, error } = await sb.from("story_questions").select("id", { count: "exact", head: true }).gte("created_at", iso);
      if (error) throw new HttpError(500, "Database non pronto: esegui supabase/domande.sql.");
      return count ?? 0;
    },
    async story(id) {
      const { data } = await sb.from("stories").select("*,story_sources(ref,source_name,title,url,published_at,excerpt)").eq("id", id).maybeSingle();
      return data as Story | null;
    },
    async history(storyId, limit) {
      const { data } = await sb.from("story_questions").select("question,answer").eq("story_id", storyId).eq("status", "ok")
        .order("created_at", { ascending: false }).limit(limit);
      return (data || []).reverse();
    },
    async saveQuestion(row) {
      const { error } = await sb.from("story_questions").insert(row);
      if (error) throw new HttpError(500, "Risposta ottenuta ma non salvata: " + error.message);
    },
  };

  const models = (Deno.env.get("GEMINI_CHAT_MODELS") || "").split(",").map((m) => m.trim()).filter(Boolean);
  try {
    const body = await req.json().catch(() => ({}));
    const result = await answerQuestion(body, db, geminiGenerate(geminiKey, fetch, Deno.env.get("GEMINI_API_BASE") || undefined), models.length ? models : DEFAULT_MODELS);
    return json(200, result);
  } catch (e) {
    if (e instanceof HttpError) return json(e.status, { error: e.message });
    console.error(e);
    return json(500, { error: "Errore imprevisto. Riprova." });
  }
});
