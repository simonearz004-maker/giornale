// Accesso ai dati (Supabase) con copia locale per la lettura offline.
import { createClient } from '@supabase/supabase-js';

const URL = import.meta.env.VITE_SUPABASE_URL;
const KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const configured = Boolean(URL && KEY);
export const sb = configured
  ? createClient(URL, KEY, { auth: { persistSession: true, autoRefreshToken: true, storageKey: 'giornale:auth' } })
  : null;

// ---------------------------------------------------------------------------
// Cache offline: ogni lettura riuscita viene salvata con l'ora di scaricamento.
// Se la rete non risponde si mostra la copia, segnalata come non aggiornata.
// ---------------------------------------------------------------------------
const CACHE_PREFIX = 'giornale:cache:';
const CACHE_MAX = 60;

function cacheSet(key, data) {
  try {
    localStorage.setItem(CACHE_PREFIX + key, JSON.stringify({ at: new Date().toISOString(), data }));
    const index = JSON.parse(localStorage.getItem(CACHE_PREFIX + '_index') || '[]').filter((k) => k !== key);
    index.unshift(key);
    for (const old of index.slice(CACHE_MAX)) localStorage.removeItem(CACHE_PREFIX + old);
    localStorage.setItem(CACHE_PREFIX + '_index', JSON.stringify(index.slice(0, CACHE_MAX)));
  } catch (e) {
    /* spazio esaurito o archivio non disponibile: si prosegue senza copia */
  }
}

function cacheGet(key) {
  try {
    return JSON.parse(localStorage.getItem(CACHE_PREFIX + key) || 'null');
  } catch (e) {
    return null;
  }
}

export const offline = { active: false, since: null, listeners: new Set() };
function setOffline(active, since = null) {
  if (offline.active === active && offline.since === since) return;
  offline.active = active;
  offline.since = since;
  offline.listeners.forEach((fn) => fn(offline));
}

const TIMEOUT_MS = 12000;
function withTimeout(promise) {
  let t;
  const timer = new Promise((_, reject) => {
    t = setTimeout(() => reject(new Error('network timeout: il server non risponde')), TIMEOUT_MS);
  });
  return Promise.race([promise, timer]).finally(() => clearTimeout(t));
}

async function cached(key, fetcher) {
  if (!navigator.onLine) {
    const copy = cacheGet(key);
    if (copy) {
      setOffline(true, copy.at);
      return copy.data;
    }
    throw new Error('Sei offline e questa pagina non è stata salvata sul dispositivo.');
  }
  try {
    const { data, error } = await withTimeout(fetcher());
    if (error) throw error;
    cacheSet(key, data);
    setOffline(false);
    return data;
  } catch (err) {
    const copy = cacheGet(key);
    const network = !navigator.onLine || /fetch|network|Failed/i.test(String(err?.message || err));
    if (copy && network) {
      setOffline(true, copy.at);
      return copy.data;
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Accesso
// ---------------------------------------------------------------------------
export async function getSession() {
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session;
}
export async function signIn(email, password) {
  const { error } = await sb.auth.signInWithPassword({ email, password });
  if (error) throw error;
}
export async function signOut() {
  await sb.auth.signOut();
  try {
    Object.keys(localStorage)
      .filter((k) => k.startsWith(CACHE_PREFIX))
      .forEach((k) => localStorage.removeItem(k));
  } catch (e) {}
}

// ---------------------------------------------------------------------------
// Lettura
// ---------------------------------------------------------------------------
const STORY_LIST = 'id,edition_date,category_slug,title,summary,relevance,is_must_read,is_update,verification_level,terms,created_at,event_date';
const STORY_FULL = '*,story_sources(ref,source_name,title,url,published_at,is_primary,fulltext_used),glossary_story_links(glossary(slug,term,simple_definition))';

export const getSettings = () => cached('settings', () => sb.from('settings').select('*').eq('id', 1).single());
export const getCategories = () =>
  cached('categories', () => sb.from('categories').select('*').order('priority', { ascending: false }).order('name'));

export const getLatestEdition = () =>
  cached('edition:latest', () =>
    sb.from('editions').select('*').order('edition_date', { ascending: false }).limit(1).maybeSingle());
export const getEdition = (date) =>
  cached(`edition:${date}`, () => sb.from('editions').select('*').eq('edition_date', date).maybeSingle());

export const getEditionStories = (editionId) =>
  cached(`stories:${editionId}`, () =>
    sb.from('stories').select(STORY_LIST).eq('edition_id', editionId).order('relevance', { ascending: false }).order('created_at'));

export const getStory = (id) => cached(`story:${id}`, () => sb.from('stories').select(STORY_FULL).eq('id', id).single());

export const getThread = (threadId, excludeId) =>
  cached(`thread:${threadId}`, () =>
    sb.from('stories').select('id,title,edition_date,is_update').eq('thread_id', threadId).neq('id', excludeId)
      .order('edition_date', { ascending: false }).limit(10));

export const getCategoryStories = (slug, { from, to, limit = 40 } = {}) =>
  cached(`cat:${slug}:${from || ''}:${to || ''}`, () => {
    let q = sb.from('stories').select(STORY_LIST).eq('category_slug', slug);
    if (from) q = q.gte('edition_date', from);
    if (to) q = q.lte('edition_date', to);
    return q.order('edition_date', { ascending: false }).order('relevance', { ascending: false }).limit(limit);
  });

export const listEditions = (limit = 60) =>
  cached('editions', () =>
    sb.from('editions').select('id,edition_date,updated_at,stories(count)').order('edition_date', { ascending: false }).limit(limit));

export async function searchStories({ q, category, from, to }) {
  let query = sb.from('stories').select(STORY_LIST);
  if (q) query = query.textSearch('search', q, { type: 'websearch', config: 'italian' });
  if (category) query = query.eq('category_slug', category);
  if (from) query = query.gte('edition_date', from);
  if (to) query = query.lte('edition_date', to);
  const { data, error } = await query.order('edition_date', { ascending: false }).limit(60);
  if (error) throw error;
  return data;
}

export const listGlossary = () =>
  cached('glossary', () => sb.from('glossary').select('slug,term,aliases,simple_definition,origin').order('term'));
export const getGlossaryEntry = (slug) =>
  cached(`glossary:${slug}`, () =>
    sb.from('glossary').select('*,glossary_story_links(stories(id,title,edition_date))').eq('slug', slug).single());

export const getRecentRuns = () =>
  cached('runs', () => sb.from('runs').select('*').order('started_at', { ascending: false }).limit(10));
export const getSources = () => cached('sources', () => sb.from('sources').select('*').order('kind').order('name'));

// ---------------------------------------------------------------------------
// Stato di lettura
// ---------------------------------------------------------------------------
export async function getStates(ids) {
  if (!ids.length || !navigator.onLine) return {};
  try {
    const { data, error } = await sb.from('user_story_state').select('*').in('story_id', ids);
    if (error) throw error;
    return Object.fromEntries(data.map((s) => [s.story_id, s]));
  } catch (e) {
    return {};
  }
}
export async function markRead(id) {
  await sb.from('user_story_state').upsert({ story_id: id, read_at: new Date().toISOString() }, { onConflict: 'story_id', ignoreDuplicates: false });
}
export async function setSaved(id, saved) {
  // l'upsert aggiorna solo le colonne indicate: la data di lettura resta invariata
  const { error } = await sb.from('user_story_state').upsert({
    story_id: id, saved, saved_at: saved ? new Date().toISOString() : null,
  });
  if (error) throw error;
}
export const listSaved = () =>
  cached('saved', () =>
    sb.from('user_story_state').select(`saved_at,stories(${STORY_LIST})`).eq('saved', true).order('saved_at', { ascending: false }));
export const listHistory = () =>
  cached('history', () =>
    sb.from('user_story_state').select(`read_at,stories(${STORY_LIST})`).not('read_at', 'is', null)
      .order('read_at', { ascending: false }).limit(100));

// ---------------------------------------------------------------------------
// Impostazioni (scrittura)
// ---------------------------------------------------------------------------
async function must(promise) {
  const { error } = await promise;
  if (error) throw error;
}
export const updateSettings = (fields) =>
  must(sb.from('settings').update({ ...fields, updated_at: new Date().toISOString() }).eq('id', 1));
export const updateCategory = (id, fields) => must(sb.from('categories').update(fields).eq('id', id));
export const createCategory = (fields) => must(sb.from('categories').insert({ ...fields, is_custom: true }));
export const deleteCategory = (id) => must(sb.from('categories').delete().eq('id', id));
export const updateSource = (id, fields) => must(sb.from('sources').update(fields).eq('id', id));
export const createSource = (fields) => must(sb.from('sources').insert(fields));

// ---------------------------------------------------------------------------
// Domande all'IA
// ---------------------------------------------------------------------------
function romeMidnightIso() {
  const now = new Date();
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome' }).format(now);
  const off = new Intl.DateTimeFormat('en-US', { timeZone: 'Europe/Rome', timeZoneName: 'shortOffset' })
    .formatToParts(now).find((p) => p.type === 'timeZoneName')?.value || 'GMT+1';
  const m = off.match(/GMT([+-])(\d{1,2})/);
  const hours = m ? (m[1] === '-' ? -1 : 1) * Number(m[2]) : 1;
  return new Date(new Date(`${day}T00:00:00Z`).getTime() - hours * 3600000).toISOString();
}

export async function getQuestions(storyId) {
  const [list, count, settings] = await Promise.all([
    sb.from('story_questions').select('question,answer,created_at').eq('story_id', storyId).eq('status', 'ok').order('created_at'),
    sb.from('story_questions').select('id', { count: 'exact', head: true }).gte('created_at', romeMidnightIso()),
    sb.from('settings').select('max_questions_per_day').eq('id', 1).maybeSingle(),
  ]);
  const err = list.error || count.error || settings.error;
  if (err) {
    const e = new Error(err.message);
    if (/story_questions|max_questions_per_day|does not exist|schema cache/i.test(err.message)) e.code = 'non_attive';
    throw e;
  }
  const limit = settings.data?.max_questions_per_day ?? 30;
  return { items: list.data || [], remaining: Math.max(0, limit - (count.count || 0)), limit };
}

export async function askQuestion(storyId, question) {
  if (!navigator.onLine) throw new Error('Per fare domande serve la connessione.');
  const { data, error } = await sb.functions.invoke('chiedi', { body: { story_id: storyId, question } });
  if (!error) return data;
  let message = 'L\'IA non ha risposto. Riprova tra poco.';
  const res = error.context;
  if (res && typeof res.json === 'function') {
    if (res.status === 404) message = 'Le domande non sono ancora attive (la funzione non è pubblicata).';
    else {
      try {
        const body = await res.json();
        if (body?.error) message = body.error;
      } catch (e) { /* risposta non leggibile */ }
    }
  } else if (/fetch|network/i.test(String(error.message))) {
    message = 'Connessione assente o servizio non raggiungibile.';
  }
  throw new Error(message);
}
