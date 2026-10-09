import * as api from '../api.js';
import { esc, fmtDateTime, storyRow } from '../ui.js';

export async function renderSaved(main, ctx) {
  const rows = (await api.listSaved()).filter((r) => r.stories);
  const state = await api.getStates(rows.map((r) => r.stories.id));
  main.innerHTML = `<div class="page page--narrow">
    <h1 class="page__title">Notizie salvate</h1>
    ${rows.length ? rows.map((r) => storyRow(r.stories, { state, categories: ctx.catBySlug, showDate: true })).join('')
      : '<p class="empty">Non hai ancora salvato notizie. Apri una notizia e usa il pulsante Salva per ritrovarla qui.</p>'}
  </div>`;
}

export async function renderHistory(main, ctx) {
  const rows = (await api.listHistory()).filter((r) => r.stories);
  const state = Object.fromEntries(rows.map((r) => [r.stories.id, { read_at: r.read_at }]));
  main.innerHTML = `<div class="page page--narrow">
    <h1 class="page__title">Cronologia</h1>
    <p class="page__lead">Le ultime 100 notizie che hai aperto.</p>
    ${rows.length ? rows.map((r) => `<div class="history-row"><p class="history-row__when">Letta ${esc(fmtDateTime(r.read_at))}</p>
      ${storyRow(r.stories, { state, categories: ctx.catBySlug, showDate: true })}</div>`).join('')
      : '<p class="empty">Le notizie che apri compariranno qui.</p>'}
  </div>`;
}
