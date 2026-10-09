import * as api from '../api.js';
import { $, $$, esc, fmtDay } from '../ui.js';

export async function renderGlossary(main) {
  const entries = await api.listGlossary();
  main.innerHTML = `<div class="page page--narrow">
    <h1 class="page__title">Glossario</h1>
    <p class="page__lead">I concetti che incontri nelle notizie, spiegati in parole semplici. Si arricchisce da solo quando compaiono termini nuovi.</p>
    <label class="field search-field"><span class="sr-only">Cerca un termine</span>
      <input type="search" id="gq" placeholder="Cerca un termine, per esempio spread" autocomplete="off" /></label>
    <ul class="glossary-list" id="glist">
      ${entries.map((g) => `<li data-text="${esc([g.term, ...(g.aliases || [])].join(' ').toLowerCase())}">
        <a href="#/glossario/${esc(g.slug)}">${esc(g.term)}</a>
        <p>${esc(g.simple_definition)}</p></li>`).join('')}
    </ul>
    <p class="empty" id="gempty" hidden>Nessun termine trovato.</p>
  </div>`;
  const input = $('#gq');
  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    let shown = 0;
    $$('#glist li').forEach((li) => {
      const ok = !q || li.dataset.text.includes(q);
      li.hidden = !ok;
      if (ok) shown++;
    });
    $('#gempty').hidden = shown > 0;
  });
}

export async function renderGlossaryEntry(main, ctx, slug) {
  const g = await api.getGlossaryEntry(slug);
  const stories = (g.glossary_story_links || []).map((l) => l.stories).filter(Boolean)
    .sort((a, b) => b.edition_date.localeCompare(a.edition_date));
  const all = g.related?.length ? await api.listGlossary() : [];
  const related = (g.related || []).map((r) => all.find((x) => x.slug === r)).filter(Boolean);
  main.innerHTML = `<div class="page page--narrow">
    <p><a href="#/glossario">Glossario</a></p>
    <article class="entry">
      <h1 class="page__title"><span class="marker">${esc(g.term)}</span></h1>
      <p class="entry__simple">${esc(g.simple_definition)}</p>
      ${g.explanation ? `<h2>Più nel dettaglio</h2><p>${esc(g.explanation)}</p>` : ''}
      ${g.example ? `<h2>Un esempio</h2><p>${esc(g.example)}</p>` : ''}
      ${related.length ? `<h2>Concetti collegati</h2><p class="markers">${related.map((r) => `<a class="marker" href="#/glossario/${esc(r.slug)}">${esc(r.term)}</a>`).join(' ')}</p>` : ''}
      ${stories.length ? `<h2>Nelle notizie</h2><ul class="thread">${stories.map((s) => `<li><a href="#/notizia/${esc(s.id)}" data-open="${esc(s.id)}">${esc(s.title)}</a> <span>${esc(fmtDay(s.edition_date))}</span></li>`).join('')}</ul>` : ''}
      <p class="entry__origin">${g.origin === 'generata'
        ? 'Voce scritta automaticamente quando il termine è comparso in una notizia, e ricontrollata da un secondo passaggio.'
        : 'Voce di base del glossario.'}</p>
    </article>
  </div>`;
}
