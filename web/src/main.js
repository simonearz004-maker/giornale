import '@fontsource-variable/literata/standard.css';
import '@fontsource-variable/literata/standard-italic.css';
import '@fontsource-variable/instrument-sans/index.css';
import './styles.css';
import * as api from './api.js';
import { $, $$, esc, errorBox, toast } from './ui.js';
import { ICONS } from './icons.js';
import { renderLogin, renderSetupNeeded } from './views/login.js';
import { renderHome } from './views/home.js';
import { renderSection, renderSections } from './views/section.js';
import { openStory, closeStory, renderStoryPage, storyIsOpen } from './views/story.js';
import { renderGlossary, renderGlossaryEntry } from './views/glossary.js';
import { renderArchive, renderArchiveDay } from './views/archive.js';
import { renderSearch } from './views/search.js';
import { renderSaved, renderHistory } from './views/library.js';
import { renderSettings } from './views/settings.js';
import { renderStatus } from './views/status.js';

export const ctx = {
  settings: null,
  categories: [],
  catBySlug: {},
  async load() {
    const [settings, categories] = await Promise.all([api.getSettings(), api.getCategories()]);
    this.settings = settings;
    this.categories = categories;
    this.catBySlug = Object.fromEntries(categories.map((c) => [c.slug, c]));
    applyDisplay(settings.display || {});
  },
};

// ---------------------------------------------------------------------------
// Visualizzazione (tema e dimensione testo): salvata sul dispositivo e nel database
// ---------------------------------------------------------------------------
export function applyDisplay(display) {
  const local = readLocalDisplay();
  const merged = { theme: 'auto', size: 'm', ...display, ...local };
  const root = document.documentElement;
  if (merged.theme === 'auto') delete root.dataset.theme;
  else root.dataset.theme = merged.theme;
  root.dataset.size = merged.size;
}
export function readLocalDisplay() {
  try {
    return JSON.parse(localStorage.getItem('giornale:display') || '{}');
  } catch (e) {
    return {};
  }
}
export function saveLocalDisplay(display) {
  try {
    localStorage.setItem('giornale:display', JSON.stringify(display));
  } catch (e) {}
}

// ---------------------------------------------------------------------------
// Struttura della pagina
// ---------------------------------------------------------------------------
function shell() {
  const name = ctx.settings?.newspaper_name || 'Il Mio Giornale';
  const sections = ctx.categories.filter((c) => c.enabled);
  $('#app').innerHTML = `
    <header class="topbar">
      <div class="topbar__inner">
        <a class="brand" href="#/">${esc(name)}</a>
        <nav class="topnav" aria-label="Sezioni">
          ${sections.map((c) => `<a href="#/sezione/${esc(c.slug)}" data-nav="sezione/${esc(c.slug)}">${esc(c.name)}</a>`).join('')}
        </nav>
        <div class="topbar__tools">
          <a href="#/cerca" class="iconlink" data-nav="cerca" aria-label="Cerca">${ICONS.search}<span>Cerca</span></a>
          <a href="#/glossario" class="iconlink hide-sm" data-nav="glossario">${ICONS.book}<span>Glossario</span></a>
          <a href="#/archivio" class="iconlink hide-sm" data-nav="archivio">${ICONS.archive}<span>Archivio</span></a>
          <a href="#/salvate" class="iconlink hide-sm" data-nav="salvate">${ICONS.bookmark}<span>Salvate</span></a>
          <a href="#/impostazioni" class="iconlink hide-sm" data-nav="impostazioni" aria-label="Impostazioni">${ICONS.gear}</a>
        </div>
      </div>
    </header>
    <div id="offline-banner" class="offline" hidden></div>
    <main id="main" tabindex="-1"></main>
    <nav class="tabbar" aria-label="Navigazione principale">
      <a href="#/" data-nav="">${ICONS.home}<span>Oggi</span></a>
      <a href="#/sezioni" data-nav="sezioni">${ICONS.list}<span>Sezioni</span></a>
      <a href="#/cerca" data-nav="cerca">${ICONS.search}<span>Cerca</span></a>
      <a href="#/salvate" data-nav="salvate">${ICONS.bookmark}<span>Salvate</span></a>
      <a href="#/altro" data-nav="altro">${ICONS.more}<span>Altro</span></a>
    </nav>
    <div id="sheet-root"></div>`;
  updateOfflineBanner(api.offline);
}

function updateOfflineBanner(state) {
  const el = $('#offline-banner');
  if (!el) return;
  if (state.active) {
    el.hidden = false;
    el.innerHTML = `Sei offline. Stai leggendo la copia salvata ${state.since ? `il ${esc(new Date(state.since).toLocaleString('it-IT', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }))}` : ''}: le notizie potrebbero non essere le più recenti.`;
  } else {
    el.hidden = true;
  }
}
api.offline.listeners.add(updateOfflineBanner);

function renderMore(main) {
  main.innerHTML = `<div class="page page--narrow">
    <h1 class="page__title">Altro</h1>
    <ul class="linklist">
      <li><a href="#/glossario">Glossario</a><span>I concetti spiegati in parole semplici</span></li>
      <li><a href="#/archivio">Archivio</a><span>Le edizioni dei giorni precedenti</span></li>
      <li><a href="#/cronologia">Cronologia</a><span>Le notizie che hai letto</span></li>
      <li><a href="#/impostazioni">Impostazioni</a><span>Sezioni, orari, fonti, aspetto</span></li>
      <li><a href="#/stato">Stato del sistema</a><span>Aggiornamenti, fonti, notizie escluse</span></li>
    </ul>
  </div>`;
}

// ---------------------------------------------------------------------------
// Instradamento
// ---------------------------------------------------------------------------
const routes = [
  [/^$/, (m, p) => renderHome(m, ctx)],
  [/^sezioni$/, (m) => renderSections(m, ctx)],
  [/^sezione\/([\w-]+)$/, (m, p) => renderSection(m, ctx, p[1])],
  [/^glossario$/, (m) => renderGlossary(m, ctx)],
  [/^glossario\/([\w-]+)$/, (m, p) => renderGlossaryEntry(m, ctx, p[1])],
  [/^archivio$/, (m) => renderArchive(m, ctx)],
  [/^archivio\/(\d{4}-\d{2}-\d{2})$/, (m, p) => renderArchiveDay(m, ctx, p[1])],
  [/^cerca$/, (m, p, q) => renderSearch(m, ctx, q)],
  [/^salvate$/, (m) => renderSaved(m, ctx)],
  [/^cronologia$/, (m) => renderHistory(m, ctx)],
  [/^impostazioni$/, (m) => renderSettings(m, ctx)],
  [/^stato$/, (m) => renderStatus(m, ctx)],
  [/^altro$/, (m) => renderMore(m)],
];

let background = null; // percorso della pagina sotto il pannello della notizia

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  return { path: decodeURIComponent(path), query: new URLSearchParams(query) };
}

async function route() {
  const { path, query } = parseHash();
  const storyMatch = path.match(/^notizia\/([\w-]+)$/);
  if (storyMatch) {
    if (background !== null) {
      openStory(storyMatch[1], ctx);
      return;
    }
    // link diretto (es. condiviso): la notizia occupa la pagina
    const main = $('#main');
    highlightNav('');
    await renderStoryPage(main, ctx, storyMatch[1]);
    return;
  }
  if (storyIsOpen()) closeStory({ silent: true });
  if (background === path + '?' + query.toString()) return; // stessa pagina: si conserva lo scorrimento
  background = path + '?' + query.toString();
  document.body.dataset.route = path === '' ? 'home' : path.split('/')[0];
  const main = $('#main');
  highlightNav(path);
  main.scrollTop = 0;
  const found = routes.find(([rx]) => rx.test(path));
  if (!found) {
    main.innerHTML = `<div class="page page--narrow"><h1 class="page__title">Pagina non trovata</h1><p><a href="#/">Torna all'edizione di oggi</a></p></div>`;
    return;
  }
  main.innerHTML = '<div class="loading" aria-busy="true">Caricamento…</div>';
  try {
    await found[1](main, path.match(found[0]), query);
  } catch (err) {
    console.error(err);
    main.innerHTML = `<div class="page page--narrow">${errorBox(err, location.hash)}</div>`;
  }
  main.focus({ preventScroll: true });
}

function highlightNav(path) {
  $$('[data-nav]').forEach((a) => {
    const target = a.dataset.nav;
    const active = target === '' ? path === '' : path === target || path.startsWith(target + '/');
    a.classList.toggle('active', active);
    if (active) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
}

// Apertura delle notizie nel pannello, senza perdere il punto della pagina
document.addEventListener('click', (e) => {
  const link = e.target.closest('a[data-open]');
  if (link && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
    e.preventDefault();
    if (background === null) background = '';
    history.pushState({ story: true }, '', `#/notizia/${link.dataset.open}`);
    openStory(link.dataset.open, ctx);
  }
  if (e.target.closest('[data-reload]')) {
    e.preventDefault();
    background = null;
    route();
  }
});
window.addEventListener('hashchange', route);
window.addEventListener('popstate', () => {
  if (!location.hash.startsWith('#/notizia/') && storyIsOpen()) closeStory({ silent: true });
});

export function refreshShell() {
  // aggiorna nome del giornale e menu delle sezioni senza ridisegnare la pagina
  const brand = $('.brand');
  if (brand) brand.textContent = ctx.settings?.newspaper_name || 'Il Mio Giornale';
  const nav = $('.topnav');
  if (nav) {
    nav.innerHTML = ctx.categories.filter((c) => c.enabled)
      .map((c) => `<a href="#/sezione/${esc(c.slug)}" data-nav="sezione/${esc(c.slug)}">${esc(c.name)}</a>`).join('');
    highlightNav(parseHash().path);
  }
}

export function rerender() {
  background = null;
  route();
}

// ---------------------------------------------------------------------------
// Avvio
// ---------------------------------------------------------------------------
async function start() {
  if (!api.configured) {
    renderSetupNeeded($('#app'));
    return;
  }
  const session = await api.getSession();
  if (!session) {
    renderLogin($('#app'), async () => start());
    return;
  }
  try {
    await ctx.load();
  } catch (err) {
    const msg = String(err?.message || err);
    $('#app').innerHTML = `<div class="page page--narrow"><div class="notice notice--error" role="alert">
      <p><strong>Accesso riuscito, ma non riesco a leggere il giornale.</strong> ${esc(msg)}</p>
      <p>Se è il primo avvio, controlla che in Supabase l'email del proprietario (tabella settings) sia la stessa con cui hai fatto l'accesso.</p>
      <p><button class="btn" id="logout">Esci</button></p></div></div>`;
    $('#logout').onclick = async () => { await api.signOut(); start(); };
    return;
  }
  shell();
  background = null;
  route();
}

api.sb?.auth.onAuthStateChange((event) => {
  if (event === 'SIGNED_OUT') start();
});

export async function logout() {
  await api.signOut();
  toast('Sei uscito.');
}

start();
