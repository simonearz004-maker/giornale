import * as api from '../api.js';
import { $, esc, storyRow } from '../ui.js';

export async function renderSearch(main, ctx, query) {
  const q = query.get('q') || '';
  const cat = query.get('cat') || '';
  const from = query.get('dal') || '';
  const to = query.get('al') || '';
  main.innerHTML = `<div class="page page--narrow">
    <h1 class="page__title">Cerca</h1>
    <form id="sform" class="form form--search" role="search">
      <label class="field search-field"><span class="sr-only">Parole da cercare</span>
        <input type="search" name="q" value="${esc(q)}" placeholder="Per esempio: tassi Bce, manovra, Stellantis" autocomplete="off" /></label>
      <div class="filters">
        <label class="field field--inline"><span>Sezione</span>
          <select name="cat"><option value="">Tutte</option>
            ${ctx.categories.map((c) => `<option value="${esc(c.slug)}" ${c.slug === cat ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}
          </select></label>
        <label class="field field--inline"><span>Dal</span><input type="date" name="dal" value="${esc(from)}" /></label>
        <label class="field field--inline"><span>al</span><input type="date" name="al" value="${esc(to)}" /></label>
      </div>
      <button class="btn btn--primary" type="submit">Cerca</button>
    </form>
    <div id="sresults"></div>
  </div>`;
  const form = $('#sform');
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const p = new URLSearchParams();
    for (const k of ['q', 'cat', 'dal', 'al']) if (form[k].value.trim()) p.set(k, form[k].value.trim());
    location.hash = `#/cerca?${p.toString()}`;
  });
  if (!q && !cat && !from && !to) {
    form.q.focus();
    return;
  }
  const box = $('#sresults');
  box.innerHTML = '<div class="loading" aria-busy="true">Ricerca…</div>';
  try {
    const results = await api.searchStories({ q, category: cat, from, to });
    const state = await api.getStates(results.map((s) => s.id));
    box.innerHTML = results.length
      ? `<p class="page__note">${results.length === 60 ? 'Primi 60 risultati' : `${results.length} risultati`}, dal più recente.</p>` +
        results.map((s) => storyRow(s, { state, categories: ctx.catBySlug, showDate: true })).join('')
      : '<p class="empty">Nessuna notizia trovata. Prova con parole diverse o allarga le date.</p>';
  } catch (err) {
    box.innerHTML = `<div class="notice notice--error"><p>${navigator.onLine ? 'Ricerca non riuscita: ' + esc(err.message) : 'La ricerca richiede la connessione.'}</p></div>`;
  }
}
