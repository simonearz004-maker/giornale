-- =====================================================================
-- Il Mio Giornale: avvio puntuale dell'edizione dal database (Supabase)
--
-- Perché serve: GitHub non garantisce gli orari dei job pianificati e su
-- questo repository ne salta molti. Qui è Supabase che, ogni 10 minuti,
-- controlla l'orario scelto nelle Impostazioni e, se l'edizione non è
-- ancora uscita, chiede a GitHub di avviarla. Il pianificatore di GitHub
-- resta attivo come riserva.
--
-- Da eseguire UNA volta in Supabase > SQL Editor, DOPO aver sostituito
-- INCOLLA_QUI_IL_TOKEN (riga 25) con il token di GitHub.
-- Il token resta cifrato nel Vault di Supabase e non è leggibile dal sito.
-- =====================================================================

create extension if not exists pg_cron;
create extension if not exists pg_net;

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

-- 1. Token di GitHub nel Vault (rieseguendo il file, il token viene aggiornato)
do $$
declare
  v_id uuid;
  v_token text := 'INCOLLA_QUI_IL_TOKEN';
begin
  if v_token = 'INCOLLA_QUI_IL_TOKEN' or length(v_token) < 20 then
    raise exception 'Sostituisci INCOLLA_QUI_IL_TOKEN con il token di GitHub prima di eseguire.';
  end if;
  select id into v_id from vault.secrets where name = 'giornale_github_token';
  if v_id is null then
    perform vault.create_secret(v_token, 'giornale_github_token', 'Token GitHub per avviare l''edizione');
  else
    perform vault.update_secret(v_id, v_token);
  end if;
end $$;

-- 2. Registro delle richieste inviate a GitHub (per non ripeterle a raffica)
create table if not exists private.avvii (
  id          bigserial primary key,
  slot        text not null,
  inviato_at  timestamptz not null default now(),
  request_id  bigint
);

-- 3. Decide se avviare l'edizione e, nel caso, chiama GitHub
create or replace function private.avvia_edizione()
returns text
language plpgsql
security definer
set search_path = public, private, extensions
as $$
declare
  v_now     timestamp := now() at time zone 'Europe/Rome';
  v_hours   int[];
  v_h       int;
  v_slot    text;
  v_token   text;
  v_req     bigint;
begin
  select update_hours into v_hours from public.settings where id = 1;
  if v_hours is null then
    return 'impostazioni assenti';
  end if;

  foreach v_h in array v_hours loop
    -- finestra: dall'orario scelto fino a 6 ore dopo (come la pipeline)
    if extract(hour from v_now)::int < v_h or extract(hour from v_now)::int > v_h + 6 then
      continue;
    end if;
    v_slot := to_char(v_now, 'YYYY-MM-DD') || 'T' || lpad(v_h::text, 2, '0');

    -- edizione già uscita per questo orario
    if exists (select 1 from public.runs r where r.slot = v_slot and r.status in ('success', 'partial')) then
      continue;
    end if;
    -- edizione in corso
    if exists (select 1 from public.runs r where r.slot = v_slot and r.status = 'running'
               and r.started_at > now() - interval '90 minutes') then
      return 'in corso: ' || v_slot;
    end if;
    -- troppi tentativi falliti: si aspetta il prossimo orario
    if (select count(*) from public.runs r where r.slot = v_slot and r.status = 'failed') >= 3 then
      continue;
    end if;
    -- richiesta già inviata da poco (GitHub impiega qualche minuto ad avviare il job)
    if exists (select 1 from private.avvii a where a.slot = v_slot and a.inviato_at > now() - interval '35 minutes') then
      return 'richiesta già inviata: ' || v_slot;
    end if;

    select decrypted_secret into v_token from vault.decrypted_secrets where name = 'giornale_github_token';
    if v_token is null then
      return 'token assente';
    end if;

    select net.http_post(
      url := 'https://api.github.com/repos/simonearz004-maker/giornale/actions/workflows/edizione.yml/dispatches',
      headers := jsonb_build_object(
        'Authorization', 'Bearer ' || v_token,
        'Accept', 'application/vnd.github+json',
        'X-GitHub-Api-Version', '2022-11-28',
        'User-Agent', 'il-mio-giornale-supabase',
        'Content-Type', 'application/json'),
      body := jsonb_build_object('ref', 'main', 'inputs', jsonb_build_object('subito', 'false'))
    ) into v_req;

    insert into private.avvii (slot, request_id) values (v_slot, v_req);
    return 'avvio richiesto: ' || v_slot;
  end loop;
  return 'niente da fare';
end;
$$;

revoke all on function private.avvia_edizione() from public, anon, authenticated;

-- 4. Controllo ogni 10 minuti (rieseguendo il file, il job viene sostituito)
select cron.schedule('giornale-avvio-edizione', '*/10 * * * *', $$select private.avvia_edizione()$$);

-- 5. Controllo: deve restituire una riga "attivo = true"
select jobname, schedule, active as attivo from cron.job where jobname = 'giornale-avvio-edizione';
