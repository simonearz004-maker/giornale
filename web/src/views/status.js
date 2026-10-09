import * as api from '../api.js';
import { esc, fmtDateTime } from '../ui.js';

const STATUS = { success: 'Completato', partial: 'Completato in parte', failed: 'Non riuscito', running: 'In corso' };

export async function renderStatus(main) {
  const [runs, sources] = await Promise.all([api.getRecentRuns(), api.getSources()]);
  const broken = sources.filter((s) => s.enabled && s.last_status === 'errore');
  main.innerHTML = `<div class="page page--narrow">
    <h1 class="page__title">Stato del sistema</h1>
    <p class="page__lead">Le ultime esecuzioni dell'aggiornamento automatico, con le notizie escluse dai controlli e il motivo.</p>
    ${broken.length ? `<div class="notice"><p><strong>Fonti che non rispondono:</strong> ${broken.map((s) => esc(s.name)).join(', ')}. Puoi disattivarle dalle <a href="#/impostazioni">impostazioni</a>.</p></div>` : ''}
    ${runs.length ? runs.map((r) => `<section class="run run--${esc(r.status)}">
      <h2>${esc(fmtDateTime(r.started_at))}: ${esc(STATUS[r.status] || r.status)}</h2>
      <p>${r.stories_published} notizie pubblicate, ${r.stories_rejected} escluse, ${r.items_fetched} articoli nuovi raccolti, ${r.requests_used} richieste al modello${r.models_used?.length ? ` (${esc(r.models_used.join(', '))})` : ''}.</p>
      ${(r.errors || []).length ? `<ul class="run__errors">${r.errors.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>` : ''}
      ${(r.rejections || []).length ? `<details><summary>Notizie escluse (${r.rejections.length})</summary>
        <ul class="run__rejections">${r.rejections.map((x) => `<li><strong>${esc(x.titolo)}</strong><br />${esc(x.motivo)}</li>`).join('')}</ul></details>` : ''}
    </section>`).join('') : '<p class="empty">Nessuna esecuzione registrata finora.</p>'}
  </div>`;
}
