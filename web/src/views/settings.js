import * as api from '../api.js';
import { applyDisplay, readLocalDisplay, saveLocalDisplay, refreshShell, rerender } from '../main.js';
import { $, $$, esc, fmtDateTime, toast } from '../ui.js';

const PRIORITY = { 5: 'Massima', 4: 'Alta', 3: 'Media', 2: 'Bassa', 1: 'Minima' };
const HOURS = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 22];

export async function renderSettings(main, ctx) {
  await ctx.load();
  const [sources, session] = await Promise.all([api.getSources(), api.getSession()]);
  const s = ctx.settings;
  const display = { theme: 'auto', size: 'm', ...(s.display || {}), ...readLocalDisplay() };
  const hours = new Set((s.update_hours || [7]).map(Number));

  main.innerHTML = `<div class="page page--narrow settings">
    <h1 class="page__title">Impostazioni</h1>
    <p class="page__lead">Le modifiche si salvano da sole. Quelle su sezioni, fonti e argomenti valgono dalla prossima edizione.</p>

    <section class="part">
      <h2>Il giornale</h2>
      <label class="field"><span>Nome del giornale</span>
        <input id="s-name" type="text" maxlength="60" value="${esc(s.newspaper_name)}" /></label>
      <fieldset class="field"><legend>Tema</legend>
        <div class="segmented">${[['auto', 'Come il sistema'], ['light', 'Chiaro'], ['dark', 'Scuro']].map(([v, l]) =>
          `<label><input type="radio" name="theme" value="${v}" ${display.theme === v ? 'checked' : ''} /><span>${l}</span></label>`).join('')}</div>
      </fieldset>
      <fieldset class="field"><legend>Dimensione del testo</legend>
        <div class="segmented">${[['s', 'Piccolo'], ['m', 'Normale'], ['l', 'Grande'], ['xl', 'Molto grande']].map(([v, l]) =>
          `<label><input type="radio" name="size" value="${v}" ${display.size === v ? 'checked' : ''} /><span>${l}</span></label>`).join('')}</div>
      </fieldset>
      <label class="field"><span>Lingua</span>
        <select disabled><option>Italiano</option></select>
        <small>Per ora il giornale è scritto solo in italiano.</small></label>
    </section>

    <section class="part">
      <h2>Aggiornamento</h2>
      <fieldset class="field"><legend>Orari delle edizioni (ora italiana)</legend>
        <div class="hours">${HOURS.map((h) => `<label><input type="checkbox" name="hour" value="${h}" ${hours.has(h) ? 'checked' : ''} /><span>${String(h).padStart(2, '0')}:00</span></label>`).join('')}</div>
        <small>Puoi scegliere fino a 3 orari. Ogni aggiornamento usa la quota gratuita di Gemini: con più orari, ciascuna edizione avrà meno notizie a disposizione. Gli orari possono slittare di qualche minuto.</small>
      </fieldset>
      <label class="field"><span>Notizie da non perdere</span>
        <select id="s-must">${[3, 4, 5, 6, 7, 8].map((n) => `<option ${n === s.max_must_read ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
    </section>

    <section class="part">
      <h2>Sezioni</h2>
      <p class="part__note">Priorità più alta significa più spazio e posizione più in alto in homepage. Il numero è il massimo di notizie per edizione.</p>
      <ul class="cat-list">${ctx.categories.map(categoryItem).join('')}</ul>
      <details class="adder">
        <summary>Aggiungi una sezione</summary>
        <form id="new-cat" class="form">
          <label class="field"><span>Nome</span><input name="name" required maxlength="40" placeholder="Per esempio: Energia" /></label>
          <label class="field"><span>Descrizione</span><input name="description" maxlength="140" /></label>
          <label class="field"><span>Argomenti seguiti (uno per riga)</span><textarea name="subtopics" rows="4" placeholder="Prezzo del gas&#10;Rinnovabili&#10;Bollette"></textarea></label>
          <label class="field"><span>Parole chiave (separate da virgole)</span><input name="keywords" placeholder="gas, Ttf, bollette, Enel" /></label>
          <button class="btn btn--primary" type="submit">Aggiungi la sezione</button>
        </form>
      </details>
    </section>

    <section class="part">
      <h2>Argomenti da escludere</h2>
      <p class="part__note">Le notizie che contengono queste parole non verranno considerate.</p>
      <div class="chips" id="excluded">${(s.excluded_topics || []).map(chip).join('')}</div>
      <form id="add-excl" class="inline-form">
        <label class="field field--grow"><span class="sr-only">Nuovo argomento da escludere</span><input name="w" placeholder="Per esempio: calciomercato" maxlength="40" /></label>
        <button class="btn" type="submit">Escludi</button>
      </form>
    </section>

    <section class="part">
      <h2>Fonti</h2>
      <p class="part__note">Le fonti preferite hanno la precedenza quando più testate raccontano lo stesso fatto. Lo stato è quello dell'ultimo controllo automatico.</p>
      <ul class="source-list">${sources.map(sourceItem).join('')}</ul>
      <details class="adder">
        <summary>Aggiungi una fonte</summary>
        <form id="new-src" class="form">
          <label class="field"><span>Nome</span><input name="name" required maxlength="60" /></label>
          <label class="field"><span>Indirizzo del feed RSS</span><input name="feed_url" type="url" required placeholder="https://…" /></label>
          <label class="field"><span>Tipo</span><select name="kind"><option value="testata">Testata giornalistica</option><option value="primaria">Fonte ufficiale (istituzione, ente, azienda)</option></select></label>
          <label class="check"><input type="checkbox" name="allow_fulltext" checked /> <span>Leggi il testo completo degli articoli, se il sito lo consente. Togli la spunta per i siti con abbonamento.</span></label>
          <button class="btn btn--primary" type="submit">Aggiungi la fonte</button>
          <small>Verrà controllata alla prossima edizione: se non risponde lo vedrai qui e nello stato del sistema.</small>
        </form>
      </details>
    </section>

    <section class="part">
      <h2>Account</h2>
      <p>Accesso eseguito come <strong>${esc(session?.user?.email || '')}</strong>.</p>
      <p><a href="#/stato">Stato del sistema</a></p>
      <button class="btn" id="logout">Esci</button>
    </section>
  </div>`;

  bind(main, ctx);
}

function categoryItem(c) {
  return `<li class="cat" data-id="${esc(c.id)}">
    <div class="cat__head">
      <label class="switch"><input type="checkbox" data-f="enabled" ${c.enabled ? 'checked' : ''} /><span class="sr-only">Attiva</span></label>
      <strong>${esc(c.name)}</strong>
    </div>
    <div class="cat__controls">
      <label class="field field--inline"><span>Priorità</span>
        <select data-f="priority">${[5, 4, 3, 2, 1].map((p) => `<option value="${p}" ${p === c.priority ? 'selected' : ''}>${PRIORITY[p]}</option>`).join('')}</select></label>
      <label class="field field--inline"><span>Max notizie</span>
        <input type="number" min="0" max="15" data-f="max_items" value="${c.max_items}" /></label>
      <label class="check"><input type="checkbox" data-f="show_on_home" ${c.show_on_home ? 'checked' : ''} /> <span>In homepage</span></label>
    </div>
    <details class="cat__more"><summary>Argomenti e parole chiave</summary>
      <label class="field"><span>Nome</span><input data-f="name" value="${esc(c.name)}" maxlength="40" /></label>
      <label class="field"><span>Descrizione</span><input data-f="description" value="${esc(c.description)}" maxlength="140" /></label>
      <label class="field"><span>Argomenti seguiti (uno per riga)</span><textarea data-f="subtopics" rows="5">${esc((c.subtopics || []).join('\n'))}</textarea></label>
      <label class="field"><span>Parole chiave (separate da virgole)</span><input data-f="keywords" value="${esc((c.keywords || []).join(', '))}" /></label>
      <button class="btn btn--danger" data-delete>Elimina la sezione</button>
    </details>
  </li>`;
}

function sourceItem(src) {
  const status = src.last_status === 'ok' ? 'Funziona' : src.last_status === 'vuoto' ? 'Nessuna notizia' : src.last_status === 'errore' ? 'Non risponde' : 'Non ancora controllata';
  return `<li class="src" data-id="${esc(src.id)}">
    <label class="switch"><input type="checkbox" data-f="enabled" ${src.enabled ? 'checked' : ''} /><span class="sr-only">Attiva</span></label>
    <div class="src__body">
      <strong>${esc(src.name)}</strong> <span class="src__kind">${src.kind === 'primaria' ? 'Fonte ufficiale' : 'Testata'}${src.allow_fulltext ? '' : ', solo sommari'}</span>
      <p class="src__status src__status--${esc(src.last_status || 'na')}">${status}${src.last_checked_at ? `, ${esc(fmtDateTime(src.last_checked_at))}` : ''}${src.last_status === 'errore' && src.last_error ? ` (${esc(src.last_error.slice(0, 80))})` : ''}</p>
    </div>
    <label class="check"><input type="checkbox" data-f="preferred" ${src.preferred ? 'checked' : ''} /> <span>Preferita</span></label>
  </li>`;
}

const chip = (w) => `<span class="chip">${esc(w)} <button type="button" data-remove="${esc(w)}" aria-label="Togli ${esc(w)}">×</button></span>`;

function slugify(t) {
  return t.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 50);
}

async function save(promise, ok = 'Salvato.') {
  try {
    await promise;
    toast(ok);
    return true;
  } catch (e) {
    toast('Non salvato: ' + e.message);
    return false;
  }
}

function bind(main, ctx) {
  const s = ctx.settings;

  $('#s-name').addEventListener('change', async (e) => {
    const name = e.target.value.trim() || 'Il Mio Giornale';
    if (await save(api.updateSettings({ newspaper_name: name }))) {
      ctx.settings.newspaper_name = name;
      refreshShell();
    }
  });

  $$('input[name="theme"], input[name="size"]', main).forEach((el) => el.addEventListener('change', () => {
    const display = { theme: $('input[name="theme"]:checked').value, size: $('input[name="size"]:checked').value };
    saveLocalDisplay(display);
    applyDisplay(display);
    api.updateSettings({ display }).catch(() => {});
  }));

  $$('input[name="hour"]', main).forEach((el) => el.addEventListener('change', async () => {
    const checked = $$('input[name="hour"]:checked', main).map((x) => Number(x.value));
    if (checked.length === 0 || checked.length > 3) {
      el.checked = !el.checked;
      toast(checked.length === 0 ? 'Serve almeno un orario.' : 'Al massimo 3 orari.');
      return;
    }
    if (await save(api.updateSettings({ update_hours: checked }), 'Orari salvati.')) ctx.settings.update_hours = checked;
  }));

  $('#s-must').addEventListener('change', (e) => save(api.updateSettings({ max_must_read: Number(e.target.value) })));

  // Sezioni
  $$('.cat', main).forEach((li) => {
    const id = li.dataset.id;
    li.querySelectorAll('[data-f]').forEach((el) => el.addEventListener('change', async () => {
      const f = el.dataset.f;
      let v = el.type === 'checkbox' ? el.checked : el.value;
      if (f === 'priority' || f === 'max_items') v = Math.max(0, Math.min(15, Number(v) || 0));
      if (f === 'subtopics') v = v.split('\n').map((x) => x.trim()).filter(Boolean);
      if (f === 'keywords') v = v.split(',').map((x) => x.trim()).filter(Boolean);
      if (f === 'name' && !v.trim()) return toast('Il nome non può essere vuoto.');
      if (await save(api.updateCategory(id, { [f]: v }))) {
        await ctx.load();
        if (f === 'enabled' || f === 'name') refreshShell();
      }
    }));
    li.querySelector('[data-delete]').addEventListener('click', async () => {
      const name = li.querySelector('strong').textContent;
      if (!confirm(`Eliminare la sezione «${name}»? Le notizie già pubblicate restano nell'archivio.`)) return;
      if (await save(api.deleteCategory(id), 'Sezione eliminata.')) {
        await ctx.load();
        refreshShell();
        rerender();
      }
    });
  });

  $('#new-cat').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    const name = f.name.value.trim();
    let slug = slugify(name) || 'sezione';
    if (ctx.catBySlug[slug]) slug += '-' + Date.now().toString(36).slice(-4);
    const ok = await save(api.createCategory({
      slug, name, description: f.description.value.trim(),
      subtopics: f.subtopics.value.split('\n').map((x) => x.trim()).filter(Boolean),
      keywords: f.keywords.value.split(',').map((x) => x.trim()).filter(Boolean),
      priority: 3, max_items: 3,
    }), 'Sezione aggiunta.');
    if (ok) {
      await ctx.load();
      refreshShell();
      rerender();
    }
  });

  // Argomenti esclusi
  const excluded = () => $$('#excluded .chip button', main).map((b) => b.dataset.remove);
  const saveExcluded = async (list) => {
    if (await save(api.updateSettings({ excluded_topics: list }))) {
      ctx.settings.excluded_topics = list;
      $('#excluded').innerHTML = list.map(chip).join('');
    }
  };
  $('#excluded').addEventListener('click', (e) => {
    const b = e.target.closest('[data-remove]');
    if (b) saveExcluded(excluded().filter((w) => w !== b.dataset.remove));
  });
  $('#add-excl').addEventListener('submit', (e) => {
    e.preventDefault();
    const w = e.target.w.value.trim();
    if (!w) return;
    e.target.w.value = '';
    if (!excluded().some((x) => x.toLowerCase() === w.toLowerCase())) saveExcluded([...excluded(), w]);
  });

  // Fonti
  $$('.src', main).forEach((li) => li.querySelectorAll('[data-f]').forEach((el) => el.addEventListener('change',
    () => save(api.updateSource(li.dataset.id, { [el.dataset.f]: el.checked })))));
  $('#new-src').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    const url = f.feed_url.value.trim();
    if (!/^https:\/\//i.test(url)) return toast('Serve un indirizzo che inizi con https://');
    const ok = await save(api.createSource({
      name: f.name.value.trim(), feed_url: url, homepage: new URL(url).origin, kind: f.kind.value,
      allow_fulltext: f.allow_fulltext.checked, notes: 'aggiunta dalle impostazioni',
    }), 'Fonte aggiunta.');
    if (ok) rerender();
  });

  $('#logout').addEventListener('click', () => api.signOut());
}
