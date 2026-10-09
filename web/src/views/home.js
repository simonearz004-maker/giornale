import * as api from '../api.js';
import { esc, fmtDayLong, fmtDay, fmtTime, storyRow, todayRome, verificationBadge } from '../ui.js';

export async function renderHome(main, ctx) {
  const [edition, runs] = await Promise.all([api.getLatestEdition(), api.getRecentRuns().catch(() => [])]);
  const settings = ctx.settings;

  if (!edition) {
    main.innerHTML = `<div class="page">${masthead(ctx, null)}
      <div class="notice"><p><strong>Non c'è ancora nessuna edizione.</strong></p>
      <p>La prima verrà pubblicata all'orario impostato (${esc(hoursText(settings))}). Puoi anche avviarla subito da GitHub: Actions → Edizione quotidiana → Run workflow.</p>
      ${runNotice(runs[0])}</div></div>`;
    return;
  }

  const stories = await api.getEditionStories(edition.id);
  const state = await api.getStates(stories.map((s) => s.id));
  const cats = ctx.categories.filter((c) => c.enabled);

  const verified = stories.filter((s) => s.verification_level !== 'non_confermata');
  const rumors = stories.filter((s) => s.verification_level === 'non_confermata');
  const mustRead = verified.filter((s) => s.is_must_read).sort((a, b) => b.relevance - a.relevance);
  const mustIds = new Set(mustRead.map((s) => s.id));

  // Sezioni in ordine di priorità; le notizie da non perdere non si ripetono sotto.
  const sections = cats
    .filter((c) => c.show_on_home)
    .map((c) => ({ c, items: verified.filter((s) => s.category_slug === c.slug && !mustIds.has(s.id)) }));

  const empty = new Set(edition.notes?.empty_categories || []);
  const terms = [...new Set(stories.flatMap((s) => s.terms || []))].slice(0, 12);
  const glossary = terms.length ? await api.listGlossary().catch(() => []) : [];
  const termLinks = terms
    .map((t) => {
      const key = t.toLowerCase();
      const g = glossary.find((g) => g.term.toLowerCase().startsWith(key) || (g.aliases || []).some((a) => a.toLowerCase() === key));
      return g ? `<a class="marker" href="#/glossario/${esc(g.slug)}">${esc(t)}</a>` : '';
    })
    .filter(Boolean);

  const lead = mustRead[0];
  const others = mustRead.slice(1);

  main.innerHTML = `<div class="page page--home">
    ${masthead(ctx, edition)}
    ${statusNotice(edition, runs, settings)}
    <div class="home">
      <div class="home__main">
        ${lead ? `<section class="block" aria-labelledby="h-must">
          <h2 class="block__title" id="h-must">Le notizie da non perdere</h2>
          ${storyRow(lead, { state, categories: ctx.catBySlug, big: true })}
          <div class="must-others">${others.map((s) => storyRow(s, { state, categories: ctx.catBySlug })).join('')}</div>
        </section>` : ''}
        ${sections.map(({ c, items }) => sectionBlock(c, items, state, ctx, empty)).join('')}
        ${rumors.length ? `<section class="block block--muted" aria-labelledby="h-rumors">
          <h2 class="block__title" id="h-rumors">Da confermare</h2>
          <p class="block__note">Indiscrezioni o notizie senza conferma ufficiale. Tienine conto con prudenza.</p>
          ${rumors.map((s) => storyRow(s, { state, categories: ctx.catBySlug })).join('')}
        </section>` : ''}
        ${!stories.length ? `<div class="notice"><p>Nessuna notizia ha superato i controlli in questa edizione. Meglio niente che notizie non verificate: controlla lo <a href="#/stato">stato del sistema</a> per i dettagli.</p></div>` : ''}
      </div>
      <aside class="home__side">
        ${termLinks.length ? `<section class="side-block">
          <h2 class="side-block__title">Concetti di oggi</h2>
          <p class="side-block__note">Le parole chiave delle notizie, spiegate in parole semplici.</p>
          <div class="markers">${termLinks.join(' ')}</div>
          <p><a href="#/glossario">Tutto il glossario</a></p>
        </section>` : ''}
        <section class="side-block">
          <h2 class="side-block__title">Come leggere i bollini</h2>
          <ul class="legend">
            <li>${verificationBadge('fonte_primaria')} documento ufficiale</li>
            <li>${verificationBadge('confermata')} almeno due testate</li>
            <li>${verificationBadge('fonte_singola')} una sola testata</li>
            <li>${verificationBadge('non_confermata')} indiscrezione</li>
          </ul>
        </section>
        <section class="side-block">
          <h2 class="side-block__title">Edizioni precedenti</h2>
          <p><a href="#/archivio">Apri l'archivio</a></p>
        </section>
      </aside>
    </div>
  </div>`;
}

function masthead(ctx, edition) {
  const name = ctx.settings?.newspaper_name || 'Il Mio Giornale';
  return `<header class="masthead">
    <h1 class="masthead__name">${esc(name)}</h1>
    ${edition ? `<p class="masthead__date">${esc(cap(fmtDayLong(edition.edition_date)))}</p>
      <p class="masthead__updated">Aggiornato alle ${esc(fmtTime(edition.updated_at))}${edition.edition_date !== todayRome() ? ` del ${esc(fmtDay(edition.updated_at))}` : ''}</p>` : ''}
  </header>`;
}

function sectionBlock(c, items, state, ctx, empty) {
  if (!items.length) {
    if (!empty.has(c.slug)) return '';
    return `<section class="block block--empty">
      <h2 class="block__title"><a href="#/sezione/${esc(c.slug)}">${esc(c.name)}</a></h2>
      <p class="block__note">Nessuno sviluppo rilevante in questa edizione.</p></section>`;
  }
  return `<section class="block" aria-labelledby="h-${esc(c.slug)}">
    <h2 class="block__title" id="h-${esc(c.slug)}"><a href="#/sezione/${esc(c.slug)}">${esc(c.name)}</a></h2>
    ${items.map((s) => storyRow(s, { state, categories: ctx.catBySlug, showCategory: false })).join('')}
  </section>`;
}

function statusNotice(edition, runs, settings) {
  const today = todayRome();
  const last = runs[0];
  const parts = [];
  if (edition.edition_date !== today) {
    const hours = (settings.update_hours || [7]).map(Number).sort((a, b) => a - b);
    const nowHour = Number(new Intl.DateTimeFormat('it-IT', { hour: 'numeric', hour12: false, timeZone: 'Europe/Rome' }).format(new Date()));
    if (nowHour >= hours[0]) {
      parts.push(`<p><strong>L'edizione di oggi non è ancora disponibile.</strong> Stai leggendo quella di ${esc(fmtDayLong(edition.edition_date))}.</p>`);
    } else {
      parts.push(`<p>La prossima edizione è prevista alle ${String(hours[0]).padStart(2, '0')}:00. Questa è l'edizione di ${esc(fmtDayLong(edition.edition_date))}.</p>`);
    }
  }
  if (last && (last.status === 'failed' || last.status === 'partial')) parts.push(runNotice(last));
  if (!parts.length) return '';
  return `<div class="notice ${last?.status === 'failed' ? 'notice--error' : ''}" role="status">${parts.join('')}</div>`;
}

function runNotice(run) {
  if (!run || (run.status !== 'failed' && run.status !== 'partial')) return '';
  const what = run.status === 'failed' ? "L'ultimo aggiornamento non è riuscito" : "L'ultimo aggiornamento è stato completato solo in parte";
  const first = (run.errors || [])[0];
  return `<p>${what} (${esc(fmtDay(run.started_at))}, ${esc(fmtTime(run.started_at))})${first ? `: ${esc(first)}` : '.'} <a href="#/stato">Dettagli</a></p>`;
}

function hoursText(settings) {
  return (settings?.update_hours || [7]).map((h) => `${String(h).padStart(2, '0')}:00`).join(' e ');
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
