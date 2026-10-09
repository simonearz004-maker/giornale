import * as api from '../api.js';
import { $, esc } from '../ui.js';

export function renderSetupNeeded(app) {
  app.innerHTML = `<div class="page page--narrow login">
    <h1 class="masthead__name">Il Mio Giornale</h1>
    <div class="notice"><p><strong>Il sito non è ancora collegato al database.</strong></p>
    <p>Mancano le variabili VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY. Segui il passo 4 della guida nel file README.md.</p></div>
  </div>`;
}

export function renderLogin(app, onSuccess) {
  app.innerHTML = `<div class="page page--narrow login">
    <h1 class="masthead__name">Il Mio Giornale</h1>
    <p class="login__lead">Accedi per leggere l'edizione di oggi.</p>
    <form id="login-form" class="form" novalidate>
      <label class="field"><span>Email</span>
        <input type="email" name="email" autocomplete="username" required inputmode="email" /></label>
      <label class="field"><span>Password</span>
        <input type="password" name="password" autocomplete="current-password" required /></label>
      <p class="form__error" id="login-error" role="alert" hidden></p>
      <button class="btn btn--primary" type="submit">Accedi</button>
    </form>
  </div>`;
  const form = $('#login-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = $('#login-error');
    const btn = form.querySelector('button');
    err.hidden = true;
    btn.disabled = true;
    btn.textContent = 'Accesso in corso…';
    try {
      await api.signIn(form.email.value.trim(), form.password.value);
      onSuccess();
    } catch (ex) {
      const msg = /invalid/i.test(ex.message) ? 'Email o password non corrette.' : ex.message;
      err.innerHTML = esc(msg);
      err.hidden = false;
      btn.disabled = false;
      btn.textContent = 'Accedi';
    }
  });
}
