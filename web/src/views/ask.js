// "Chiedi all'IA su questa notizia": domande e risposte nel dettaglio della notizia.
import * as api from '../api.js';
import { $, esc, fmtDateTime } from '../ui.js';

const SUGGESTIONS = [
  'Spiegamelo in modo più semplice',
  'Che effetto può avere su di me?',
  'Perché è successo?',
  'Quali termini devo conoscere per capirla?',
];

export function askSection(storyId) {
  return `<section class="part ask" id="ask" aria-labelledby="h-ask" data-story="${esc(storyId)}">
    <h2 id="h-ask">Chiedi all'IA su questa notizia</h2>
    <p class="part__note">Risponde partendo dalla scheda e dalle fonti di questa notizia, citandole tra parentesi.
      Le risposte non passano i controlli delle schede: per i dati, verifica sempre sulle fonti.</p>
    <div class="ask__thread" id="ask-thread" aria-live="polite"></div>
    <div class="ask__chips" id="ask-chips">${SUGGESTIONS.map((q) => `<button type="button" class="chip-btn">${esc(q)}</button>`).join('')}</div>
    <form class="ask__form" id="ask-form">
      <label class="sr-only" for="ask-input">La tua domanda</label>
      <textarea id="ask-input" rows="2" maxlength="600" placeholder="Fai una domanda su questa notizia…"></textarea>
      <button class="btn btn--primary" type="submit" id="ask-send">Chiedi</button>
    </form>
    <p class="ask__meta" id="ask-meta"></p>
  </section>`;
}

function renderAnswer(text) {
  // testo sicuro, a capo come paragrafi, [S1] come collegamento alla fonte
  return String(text || '')
    .split(/\n{1,}/)
    .filter((p) => p.trim())
    .map((p) => `<p>${esc(p).replace(/\[(S\d+)(?:\s*,\s*(S\d+))*\]/g, (m) =>
      m.slice(1, -1).split(/\s*,\s*/).map((r) => `<a class="cite" href="#src-${r}">${r}</a>`).join(''))}</p>`)
    .join('');
}

function qa(item) {
  return `<div class="ask__item">
    <p class="ask__q">${esc(item.question)}</p>
    <div class="ask__a">${renderAnswer(item.answer)}</div>
    ${item.created_at ? `<p class="ask__when">${esc(fmtDateTime(item.created_at))}</p>` : ''}
  </div>`;
}

export async function bindAsk(container, storyId) {
  const box = $('#ask', container);
  if (!box) return;
  const thread = $('#ask-thread', box);
  const form = $('#ask-form', box);
  const input = $('#ask-input', box);
  const send = $('#ask-send', box);
  const meta = $('#ask-meta', box);

  const setMeta = (remaining, limit) => {
    if (remaining == null) return;
    meta.textContent = remaining > 0 ? `Ti restano ${remaining} domande su ${limit} per oggi.` : `Hai usato tutte le ${limit} domande di oggi.`;
  };

  if (!navigator.onLine) {
    input.disabled = send.disabled = true;
    meta.textContent = 'Per fare domande serve la connessione.';
  }

  try {
    const { items, remaining, limit } = await api.getQuestions(storyId);
    thread.innerHTML = items.map(qa).join('');
    setMeta(remaining, limit);
  } catch (e) {
    if (e.code === 'non_attive') {
      box.querySelector('.part__note').textContent = 'Le domande all\'IA non sono ancora attive su questo giornale.';
      form.hidden = true;
      $('#ask-chips', box).hidden = true;
      return;
    }
  }

  const ask = async (question) => {
    question = question.trim();
    if (question.length < 2 || send.disabled) return;
    send.disabled = true;
    input.disabled = true;
    const pending = document.createElement('div');
    pending.className = 'ask__item ask__item--pending';
    pending.innerHTML = `<p class="ask__q">${esc(question)}</p><div class="ask__a"><p class="ask__thinking">Sto leggendo le fonti…</p></div>`;
    thread.appendChild(pending);
    pending.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
      const res = await api.askQuestion(storyId, question);
      pending.outerHTML = qa({ question, answer: res.answer, created_at: new Date().toISOString() });
      input.value = '';
      setMeta(res.remaining, res.limit);
    } catch (e) {
      pending.querySelector('.ask__a').innerHTML = `<p class="ask__error">${esc(e.message)}</p>`;
      pending.classList.add('ask__item--error');
    } finally {
      send.disabled = false;
      input.disabled = false;
    }
  };

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    ask(input.value);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      ask(input.value);
    }
  });
  $('#ask-chips', box).addEventListener('click', (e) => {
    const b = e.target.closest('.chip-btn');
    if (b) ask(b.textContent);
  });
}
