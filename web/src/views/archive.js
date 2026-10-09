import * as api from '../api.js';
import { esc, fmtDay, fmtDayLong, fmtTime, storyRow } from '../ui.js';

export async function renderArchive(main) {
  const editions = await api.listEditions(120);
  const byMonth = new Map();
  for (const e of editions) {
    const key = new Intl.DateTimeFormat('it-IT', { month: 'long', year: 'numeric', timeZone: 'Europe/Rome' }).format(new Date(`${e.edition_date}T12:00:00Z`));
    if (!byMonth.has(key)) byMonth.set(key, []);
    byMonth.get(key).push(e);
  }
  main.innerHTML = `<div class="page page--narrow">
    <h1 class="page__title">Archivio</h1>
    <p class="page__lead">Tutte le edizioni pubblicate. Per cercare un argomento usa la <a href="#/cerca">ricerca</a>.</p>
    ${editions.length ? [...byMonth.entries()].map(([month, list]) => `<section class="block">
      <h2 class="block__title block__title--date">${esc(month.charAt(0).toUpperCase() + month.slice(1))}</h2>
      <ul class="archive">${list.map((e) => `<li><a href="#/archivio/${esc(e.edition_date)}">${esc(fmtDayLong(e.edition_date))}</a>
        <span>${e.stories?.[0]?.count ?? 0} notizie</span></li>`).join('')}</ul>
    </section>`).join('') : '<div class="notice"><p>L\'archivio è vuoto: la prima edizione non è ancora stata pubblicata.</p></div>'}
  </div>`;
}

export async function renderArchiveDay(main, ctx, date) {
  const edition = await api.getEdition(date);
  if (!edition) {
    main.innerHTML = `<div class="page page--narrow"><h1 class="page__title">Nessuna edizione il ${esc(fmtDay(date))}</h1><p><a href="#/archivio">Torna all'archivio</a></p></div>`;
    return;
  }
  const stories = await api.getEditionStories(edition.id);
  const state = await api.getStates(stories.map((s) => s.id));
  const order = Object.fromEntries(ctx.categories.map((c, i) => [c.slug, i]));
  stories.sort((a, b) => (order[a.category_slug] ?? 99) - (order[b.category_slug] ?? 99) || b.relevance - a.relevance);
  main.innerHTML = `<div class="page page--narrow">
    <p><a href="#/archivio">Archivio</a></p>
    <h1 class="page__title">${esc(fmtDayLong(date))}</h1>
    <p class="page__lead">Edizione aggiornata l'ultima volta alle ${esc(fmtTime(edition.updated_at))} del ${esc(fmtDay(edition.updated_at))}.</p>
    ${stories.map((s) => storyRow(s, { state, categories: ctx.catBySlug })).join('') || '<p>Nessuna notizia in questa edizione.</p>'}
  </div>`;
}
