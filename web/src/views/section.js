import * as api from '../api.js';
import { $, esc, fmtDay, storyRow } from '../ui.js';

export function renderSections(main, ctx) {
  const cats = ctx.categories.filter((c) => c.enabled);
  main.innerHTML = `<div class="page page--narrow">
    <h1 class="page__title">Sezioni</h1>
    <ul class="linklist">${cats.map((c) => `<li><a href="#/sezione/${esc(c.slug)}">${esc(c.name)}</a><span>${esc(c.description || '')}</span></li>`).join('')}</ul>
    <p class="page__note">Puoi aggiungere, togliere e riordinare le sezioni dalle <a href="#/impostazioni">impostazioni</a>.</p>
  </div>`;
}

export async function renderSection(main, ctx, slug, filters = {}) {
  const cat = ctx.catBySlug[slug];
  if (!cat) {
    main.innerHTML = `<div class="page page--narrow"><h1 class="page__title">Sezione non trovata</h1><p><a href="#/sezioni">Vedi tutte le sezioni</a></p></div>`;
    return;
  }
  const stories = await api.getCategoryStories(slug, filters);
  const state = await api.getStates(stories.map((s) => s.id));
  const byDay = new Map();
  for (const s of stories) {
    if (!byDay.has(s.edition_date)) byDay.set(s.edition_date, []);
    byDay.get(s.edition_date).push(s);
  }
  main.innerHTML = `<div class="page page--narrow">
    <h1 class="page__title">${esc(cat.name)}</h1>
    ${cat.description ? `<p class="page__lead">${esc(cat.description)}</p>` : ''}
    ${!cat.enabled ? '<div class="notice"><p>Questa sezione è disattivata: non riceve nuove notizie.</p></div>' : ''}
    <form class="filters" id="filters">
      <label class="field field--inline"><span>Dal</span><input type="date" name="from" value="${esc(filters.from || '')}" /></label>
      <label class="field field--inline"><span>al</span><input type="date" name="to" value="${esc(filters.to || '')}" /></label>
      <button class="btn" type="submit">Filtra</button>
      ${filters.from || filters.to ? '<button class="btn btn--quiet" type="button" id="clear">Tutte le date</button>' : ''}
    </form>
    ${stories.length ? [...byDay.entries()].map(([day, items]) => `<section class="block">
      <h2 class="block__title block__title--date">${esc(fmtDay(day))}</h2>
      ${items.map((s) => storyRow(s, { state, categories: ctx.catBySlug, showCategory: false })).join('')}
    </section>`).join('') : `<div class="notice"><p>Nessuna notizia ${filters.from || filters.to ? 'in queste date' : 'ancora'} per questa sezione.</p></div>`}
  </div>`;
  $('#filters').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target;
    renderSection(main, ctx, slug, { from: f.from.value || undefined, to: f.to.value || undefined });
  });
  $('#clear')?.addEventListener('click', () => renderSection(main, ctx, slug, {}));
}
