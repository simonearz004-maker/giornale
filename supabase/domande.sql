-- =====================================================================
-- Il Mio Giornale: domande all'IA sulle notizie
-- Da eseguire UNA volta in Supabase > SQL Editor (si può rieseguire).
-- =====================================================================

-- 1. Estratto del testo delle fonti, per rispondere alle domande partendo dagli articoli.
--    Resta solo nel database privato e viene cancellato dopo 30 giorni.
alter table public.story_sources add column if not exists excerpt text;

-- 2. Limite di domande al giorno (modificabile dalle Impostazioni del giornale)
alter table public.settings add column if not exists max_questions_per_day int not null default 30
  check (max_questions_per_day between 0 and 500);

-- 3. Domande e risposte
create table if not exists public.story_questions (
  id          uuid primary key default gen_random_uuid(),
  story_id    uuid not null references public.stories(id) on delete cascade,
  question    text not null check (length(question) between 2 and 600),
  answer      text not null default '',
  model       text,
  status      text not null default 'ok' check (status in ('ok', 'errore')),
  created_at  timestamptz not null default now()
);
create index if not exists story_questions_story_idx on public.story_questions (story_id, created_at);
create index if not exists story_questions_created_idx on public.story_questions (created_at desc);

alter table public.story_questions enable row level security;
drop policy if exists owner_read on public.story_questions;
create policy owner_read on public.story_questions for select to authenticated using (public.is_owner());
drop policy if exists owner_insert on public.story_questions;
create policy owner_insert on public.story_questions for insert to authenticated with check (public.is_owner());
drop policy if exists owner_delete on public.story_questions;
create policy owner_delete on public.story_questions for delete to authenticated using (public.is_owner());
revoke all on public.story_questions from anon;

-- 4. Pulizia automatica degli estratti più vecchi di 30 giorni (ogni notte alle 3)
create extension if not exists pg_cron;
select cron.schedule('giornale-pulizia-estratti', '0 3 * * *', $$
  update public.story_sources ss set excerpt = null
  from public.stories s
  where s.id = ss.story_id and ss.excerpt is not null and s.edition_date < current_date - 30
$$);

-- 5. Controllo: deve restituire "pronto"
select case when exists (select 1 from information_schema.columns
                          where table_name = 'story_sources' and column_name = 'excerpt')
             and exists (select 1 from information_schema.tables where table_name = 'story_questions')
       then 'pronto' else 'qualcosa non va' end as esito;
