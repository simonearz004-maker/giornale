import * as api from '../api.js';
import { ICONS } from '../icons.js';
import { $, esc, fmtDay, fmtDateTime, safeUrl, toast, verificationBadge, relevanceMarks, VERIFICATION, errorBox } from '../ui.js';

let openId = null;
let lastFocus = null;

export const storyIsOpen = () => openId !== null;

const IMPACT_STATE = { osservato: 'Già in corso', possibile: 'Possibile' };
const STEP_TYPE = { ufficiale: 'Deciso', programmato: 'In calendario', previsione: 'Previsione', ipotesi: 'Ipotesi' };
const NATURE = { fatto: 'Fatto', dichiarazione: 'Dichiarazione', interpretazione: 'Interpretazione' };

export async function openStory(id, ctx) {
  const root = $('#sheet-root');
  lastFocus = openId ? lastFocus : document.activeElement;
  openId = id;
  root.innerHTML = `<div class="sheet-backdrop" data-close></div>
    <div class="sheet" role="dialog" aria-modal="true" aria-label="Notizia">
      <div class="sheet__bar">
        <button class="iconbtn" data-close aria-label="Chiudi">${ICONS.close}</button>
      </div>
      <div class="sheet__body" id="sheet-body"><div class="loading" aria-busy="true">Caricamento…</div></div>
    </div>`;
  document.body.classList.add('sheet-open');
  requestAnimationFrame(() => root.classList.add('open'));
  root.querySelectorAll('[data-close]').forEach((el) => el.addEventListener('click', () => closeStory()));
  document.addEventListener('keydown', onKey);
  const body = $('#sheet-body');
  try {
    await fillStory(body, ctx, id);
  } catch (err) {
    body.innerHTML = errorBox(err);
  }
  root.querySelector('.sheet__bar button')?.focus();
}

function onKey(e) {
  if (e.key === 'Escape') closeStory();
}

export function closeStory({ silent = false } = {}) {
  const root = $('#sheet-root');
  if (!root || openId === null) return;
  openId = null;
  root.classList.remove('open');
  document.body.classList.remove('sheet-open');
  document.removeEventListener('keydown', onKey);
  setTimeout(() => { if (openId === null) root.innerHTML = ''; }, 220);
  if (!silent) {
    if (history.state?.story) history.back();
    else history.replaceState(null, '', '#/');
  }
  lastFocus?.focus?.({ preventScroll: true });
}

export async function renderStoryPage(main, ctx, id) {
  main.innerHTML = `<div class="page page--narrow"><p><a href="#/">Vai all'edizione di oggi</a></p><div id="story-page"></div></div>`;
  await fillStory($('#story-page'), ctx, id);
}

async function fillStory(container, ctx, id) {
  const s = await api.getStory(id);
  const [states, thread] = await Promise.all([api.getStates([id]), api.getThread(s.thread_id, id).catch(() => [])]);
  const state = states[id] || {};
  const cat = ctx.catBySlug[s.category_slug];
  const sources = [...(s.story_sources || [])].sort((a, b) => a.ref.localeCompare(b.ref, 'it', { numeric: true }));
  const refName = Object.fromEntries(sources.map((x) => [x.ref, x.source_name]));
  const cite = (refs) => (refs || []).filter((r) => refName[r]).map((r) => `<a class="cite" href="#src-${esc(r)}" title="${esc(refName[r])}">${esc(r)}</a>`).join('');
  const glossary = (s.glossary_story_links || []).map((l) => l.glossary).filter(Boolean);
  const v = VERIFICATION[s.verification_level] || VERIFICATION.fonte_singola;

  container.innerHTML = `<article class="article">
    <div class="article__meta">
      ${cat ? `<a class="story__cat" href="#/sezione/${esc(cat.slug)}">${esc(cat.name)}</a>` : ''}
      <span>${esc(fmtDay(s.edition_date))}</span>
      ${s.event_date && s.event_date !== s.edition_date ? `<span>fatto del ${esc(fmtDay(s.event_date))}</span>` : ''}
      ${s.is_update ? '<span class="tag">Aggiornamento</span>' : ''}
    </div>
    <h1 class="article__title">${esc(s.title)}</h1>
    <div class="article__badges">${verificationBadge(s.verification_level)} ${relevanceMarks(s.relevance)}</div>
    <p class="article__summary">${esc(s.summary)}</p>

    <div class="article__actions">
      <button class="btn" id="btn-save" aria-pressed="${state.saved ? 'true' : 'false'}">${ICONS.bookmark}<span>${state.saved ? 'Salvata' : 'Salva'}</span></button>
      <button class="btn" id="btn-share">${ICONS.share}<span>Condividi</span></button>
    </div>

    ${s.why_important?.length ? `<section class="part">
      <h2>Perché è importante</h2>
      <ul class="impacts">${s.why_important.map((i) => `<li>
        <span class="impacts__who">${esc(cap(i.chi))}</span>
        <span class="impacts__state impacts__state--${esc(i.stato)}">${esc(IMPACT_STATE[i.stato] || 'Possibile')}</span>
        <p>${esc(i.testo)}</p></li>`).join('')}</ul>
    </section>` : ''}

    ${s.explainer ? `<section class="part explainer">
      <h2><span class="marker">💡 Te lo spiego in parole semplici</span></h2>
      ${s.explainer.titolo ? `<h3>${esc(s.explainer.titolo)}</h3>` : ''}
      ${paragraphs(s.explainer.testo)}
    </section>` : ''}

    ${s.data_points?.length ? `<section class="part">
      <h2>I numeri</h2>
      <table class="data"><thead><tr><th scope="col">Dato</th><th scope="col">Valore</th><th scope="col">Periodo</th><th scope="col"><span class="sr-only">Fonte</span></th></tr></thead>
      <tbody>${s.data_points.map((d) => `<tr><th scope="row">${esc(d.etichetta)}</th><td class="num">${esc(d.valore)}</td><td>${esc(d.periodo)}</td><td>${cite([d.fonte])}</td></tr>`).join('')}</tbody></table>
    </section>` : ''}

    ${s.context ? `<section class="part"><h2>Il contesto</h2>${paragraphs(s.context)}</section>` : ''}

    ${thread.length ? `<section class="part"><h2>Le puntate precedenti</h2><ul class="thread">
      ${thread.map((t) => `<li><a href="#/notizia/${esc(t.id)}" data-open="${esc(t.id)}">${esc(t.title)}</a> <span>${esc(fmtDay(t.edition_date))}</span></li>`).join('')}
    </ul></section>` : ''}

    ${s.next_steps?.length ? `<section class="part"><h2>Che cosa potrebbe succedere adesso</h2><ul class="steps">
      ${s.next_steps.map((p) => `<li><span class="steps__type steps__type--${esc(p.tipo)}">${esc(STEP_TYPE[p.tipo] || 'Ipotesi')}</span> ${esc(p.testo)} ${cite(p.fonti)}</li>`).join('')}
    </ul></section>` : ''}

    ${s.divergences ? `<section class="part part--warn"><h2>Le fonti non sono d'accordo</h2>${paragraphs(s.divergences)}</section>` : ''}

    ${s.claims?.length ? `<section class="part"><h2>Cosa dicono esattamente le fonti</h2>
      <p class="part__note">Ogni affermazione principale con la fonte che la sostiene.</p>
      <ul class="claims">${s.claims.map((c) => `<li><span class="claims__nature">${esc(NATURE[c.natura] || 'Fatto')}</span> ${esc(c.testo)} ${cite(c.fonti)}</li>`).join('')}</ul>
    </section>` : ''}

    <section class="part sources" aria-labelledby="h-sources">
      <h2 id="h-sources">Fonti</h2>
      <ol class="sourcelist">${sources.map((x) => `<li id="src-${esc(x.ref)}">
        <span class="sourcelist__ref">${esc(x.ref)}</span>
        <div><a href="${safeUrl(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.title || x.url)} ${ICONS.external}</a>
        <p>${esc(x.source_name)}${x.is_primary ? ' (fonte ufficiale)' : ''}${x.published_at ? `, pubblicato il ${esc(fmtDateTime(x.published_at))}` : ''}.
        ${x.fulltext_used ? 'Articolo letto per intero.' : 'Usati solo titolo e sommario del feed.'}</p></div>
      </li>`).join('')}</ol>
    </section>

    ${glossary.length ? `<section class="part"><h2>Concetti collegati</h2><ul class="concepts">
      ${glossary.map((g) => `<li><a class="marker" href="#/glossario/${esc(g.slug)}">${esc(g.term)}</a> ${esc(g.simple_definition)}</li>`).join('')}
    </ul></section>` : ''}

    <section class="part verification">
      <h2>Come è stata verificata</h2>
      <p><strong>${esc(v.label)}.</strong> ${esc(v.help)}</p>
      ${(s.verification_notes || []).map((n) => `<p>${esc(n)}</p>`).join('')}
      <p>Ogni numero (esclusi gli esempi della spiegazione) è stato confrontato in automatico con il testo delle fonti, e la scheda è stata ricontrollata con un secondo passaggio. Scheda scritta con ${esc(s.model_used || 'un modello linguistico')}: se trovi un errore, le fonti qui sopra sono il riferimento.</p>
    </section>
  </article>`;

  api.markRead(id).catch(() => {});

  const saveBtn = $('#btn-save', container);
  saveBtn.addEventListener('click', async () => {
    const next = saveBtn.getAttribute('aria-pressed') !== 'true';
    try {
      await api.setSaved(id, next);
      saveBtn.setAttribute('aria-pressed', String(next));
      saveBtn.querySelector('span').textContent = next ? 'Salvata' : 'Salva';
      toast(next ? 'Notizia salvata.' : 'Notizia tolta dalle salvate.');
    } catch (e) {
      toast('Non sono riuscito a salvare: ' + e.message);
    }
  });
  $('#btn-share', container).addEventListener('click', async () => {
    const url = `${location.origin}${location.pathname}#/notizia/${id}`;
    try {
      if (navigator.share) await navigator.share({ title: s.title, url });
      else {
        await navigator.clipboard.writeText(url);
        toast('Link copiato. Si apre solo dopo aver fatto l\'accesso.');
      }
    } catch (e) {
      /* condivisione annullata */
    }
  });
  container.querySelectorAll('a.cite').forEach((a) => a.addEventListener('click', (e) => {
    e.preventDefault();
    container.querySelector(a.getAttribute('href'))?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }));
}

function paragraphs(text) {
  return String(text || '').split(/\n{1,}/).filter((p) => p.trim()).map((p) => `<p>${esc(p)}</p>`).join('');
}

const cap = (s) => String(s || '').charAt(0).toUpperCase() + String(s || '').slice(1);
