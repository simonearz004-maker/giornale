// Piccoli strumenti di interfaccia condivisi dalle pagine.

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ESC[c]);

// Solo collegamenti http(s): nessun javascript: o data: dai contenuti salvati.
export const safeUrl = (u) => (/^https?:\/\//i.test(String(u || '')) ? esc(u) : '#');

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const TZ = 'Europe/Rome';
const dFmt = new Intl.DateTimeFormat('it-IT', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: TZ });
const dShort = new Intl.DateTimeFormat('it-IT', { day: 'numeric', month: 'long', year: 'numeric', timeZone: TZ });
const tFmt = new Intl.DateTimeFormat('it-IT', { hour: '2-digit', minute: '2-digit', timeZone: TZ });
const dtFmt = new Intl.DateTimeFormat('it-IT', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: TZ });

// le date "AAAA-MM-GG" sono date del calendario italiano: le si interpreta a mezzogiorno per evitare slittamenti di fuso
const asDate = (v) => (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) ? new Date(`${v}T12:00:00Z`) : new Date(v));
export const fmtDayLong = (v) => (v ? dFmt.format(asDate(v)) : '');
export const fmtDay = (v) => (v ? dShort.format(asDate(v)) : '');
export const fmtTime = (v) => (v ? tFmt.format(new Date(v)) : '');
export const fmtDateTime = (v) => (v ? dtFmt.format(new Date(v)) : '');

export function todayRome() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date());
}

export const VERIFICATION = {
  fonte_primaria: { label: 'Fonte primaria', help: 'Sostenuta da un documento ufficiale (istituzione, ente statistico, banca centrale, azienda).' },
  confermata: { label: 'Confermata', help: 'Riportata da almeno due testate indipendenti.' },
  fonte_singola: { label: 'Fonte singola', help: 'Riportata da una sola testata: nessuna conferma indipendente disponibile.' },
  non_confermata: { label: 'Da confermare', help: 'Indiscrezione o notizia senza conferma ufficiale.' },
};

export const RELEVANCE = { 5: 'Rilevanza molto alta', 4: 'Rilevanza alta', 3: 'Rilevanza media', 2: 'Rilevanza bassa', 1: 'Rilevanza bassa' };

export function verificationBadge(level) {
  const v = VERIFICATION[level] || VERIFICATION.fonte_singola;
  return `<span class="badge badge--${esc(level)}" title="${esc(v.help)}">${esc(v.label)}</span>`;
}

export function relevanceMarks(n) {
  const filled = Math.max(1, Math.min(5, Number(n) || 3));
  return `<span class="relevance" title="${esc(RELEVANCE[filled])}" aria-label="${esc(RELEVANCE[filled])}">${'<i class="on"></i>'.repeat(filled)}${'<i></i>'.repeat(5 - filled)}</span>`;
}

export function toast(message) {
  let el = $('#toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    el.setAttribute('role', 'status');
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), 2600);
}

export function errorBox(err, retryHref) {
  const msg = String(err?.message || err || 'Errore sconosciuto');
  return `<div class="notice notice--error" role="alert">
    <p><strong>Non riesco a caricare questa pagina.</strong> ${esc(msg)}</p>
    ${retryHref ? `<p><a href="${esc(retryHref)}" data-reload>Riprova</a></p>` : ''}
  </div>`;
}

export function storyRow(s, { state = {}, categories = {}, showDate = false, showCategory = true, big = false } = {}) {
  const cat = categories[s.category_slug];
  const read = state[s.id]?.read_at;
  return `<article class="story ${big ? 'story--lead' : ''} ${read ? 'is-read' : ''}" data-story="${esc(s.id)}">
    <div class="story__meta">
      ${showCategory && cat ? `<a class="story__cat" href="#/sezione/${esc(cat.slug)}">${esc(cat.name)}</a>` : ''}
      ${s.is_update ? '<span class="tag">Aggiornamento</span>' : ''}
      ${showDate ? `<span>${esc(fmtDay(s.edition_date))}</span>` : ''}
      ${read ? '<span class="read-mark">Già letta</span>' : ''}
    </div>
    <h3 class="story__title"><a href="#/notizia/${esc(s.id)}" data-open="${esc(s.id)}">${esc(s.title)}</a></h3>
    <p class="story__summary">${esc(big ? s.summary : firstSentences(s.summary, 2))}</p>
    <div class="story__foot">${verificationBadge(s.verification_level)} ${relevanceMarks(s.relevance)}</div>
  </article>`;
}

export function firstSentences(text, n) {
  const parts = String(text || '').match(/[^.!?]+[.!?]+(\s|$)/g);
  if (!parts || parts.length <= n) return text || '';
  return parts.slice(0, n).join('').trim();
}

export function debounce(fn, ms = 300) {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}
