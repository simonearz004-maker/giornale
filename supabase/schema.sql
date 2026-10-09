-- =====================================================================
-- Il Mio Giornale — schema del database (Supabase / PostgreSQL)
-- Da eseguire una sola volta in Supabase > SQL Editor.
-- Poi eseguire seed.sql per i dati iniziali.
-- =====================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------
-- Impostazioni (riga unica, id = 1)
-- ---------------------------------------------------------------------
create table if not exists public.settings (
  id               int primary key default 1 check (id = 1),
  newspaper_name   text not null default 'Il Mio Giornale',
  owner_email      text not null,
  timezone         text not null default 'Europe/Rome',
  update_hours     int[] not null default '{7}',            -- ore locali (0-23) in cui pubblicare
  language         text not null default 'it',
  excluded_topics  text[] not null default '{}',            -- parole/argomenti da escludere
  max_must_read    int not null default 5 check (max_must_read between 1 and 10),
  max_requests_per_run int not null default 60 check (max_requests_per_run between 10 and 300),
  display          jsonb not null default '{}'::jsonb,     -- tema, dimensione testo (sincronizzati)
  updated_at       timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Categorie modificabili
-- ---------------------------------------------------------------------
create table if not exists public.categories (
  id            uuid primary key default gen_random_uuid(),
  slug          text not null unique,
  name          text not null,
  description   text not null default '',
  subtopics     text[] not null default '{}',
  keywords      text[] not null default '{}',
  priority      int not null default 3 check (priority between 1 and 5),
  max_items     int not null default 4 check (max_items between 0 and 15),
  enabled       boolean not null default true,
  show_on_home  boolean not null default true,
  is_custom     boolean not null default false,
  created_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Fonti (feed RSS/Atom)
-- ---------------------------------------------------------------------
create table if not exists public.sources (
  id                    uuid primary key default gen_random_uuid(),
  name                  text not null,
  feed_url              text not null unique,
  homepage              text not null default '',
  kind                  text not null default 'testata' check (kind in ('primaria','testata')),
  language              text not null default 'it',
  enabled               boolean not null default true,
  preferred             boolean not null default false,
  allow_fulltext        boolean not null default true,     -- false = paywall o divieto: si usa solo il sommario del feed
  exclude_title_regex   text,                              -- es. bandi di gara nel feed ISTAT
  notes                 text not null default '',
  last_status           text,                              -- ok | errore | vuoto
  last_error            text,
  last_checked_at       timestamptz,
  last_item_count       int,
  consecutive_failures  int not null default 0,
  created_at            timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Registro delle esecuzioni della pipeline
-- ---------------------------------------------------------------------
create table if not exists public.runs (
  id                 uuid primary key default gen_random_uuid(),
  started_at         timestamptz not null default now(),
  finished_at        timestamptz,
  slot               text,                                 -- es. 2026-10-10T07 (data+ora locale)
  status             text not null default 'running'
                     check (status in ('running','success','partial','failed')),
  trigger            text not null default 'schedule',
  models_used        text[] not null default '{}',
  requests_used      int not null default 0,
  items_fetched      int not null default 0,
  clusters           int not null default 0,
  stories_published  int not null default 0,
  stories_rejected   int not null default 0,
  errors             jsonb not null default '[]'::jsonb,
  rejections         jsonb not null default '[]'::jsonb
);
create index if not exists runs_started_idx on public.runs (started_at desc);

-- ---------------------------------------------------------------------
-- Edizioni (una per giorno)
-- ---------------------------------------------------------------------
create table if not exists public.editions (
  id            uuid primary key default gen_random_uuid(),
  edition_date  date not null unique,
  published_at  timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  last_run_id   uuid references public.runs(id) on delete set null,
  notes         jsonb not null default '{}'::jsonb          -- es. {"empty_categories": ["banche"]}
);

-- ---------------------------------------------------------------------
-- Notizie (schede)
-- ---------------------------------------------------------------------
create table if not exists public.stories (
  id                  uuid primary key default gen_random_uuid(),
  edition_id          uuid not null references public.editions(id) on delete cascade,
  edition_date        date not null,
  category_id         uuid references public.categories(id) on delete set null,
  category_slug       text not null,
  thread_id           uuid not null default gen_random_uuid(), -- stesso filo per notizie in evoluzione
  is_update           boolean not null default false,
  title               text not null,
  summary             text not null,
  why_important       jsonb not null default '[]'::jsonb,  -- [{chi, testo, stato: osservato|possibile}]
  explainer           jsonb,                               -- {titolo, testo} oppure null
  data_points         jsonb not null default '[]'::jsonb,  -- [{etichetta, valore, periodo, fonte}]
  context             text not null default '',
  next_steps          jsonb not null default '[]'::jsonb,  -- [{tipo, testo, fonte}]
  claims              jsonb not null default '[]'::jsonb,  -- [{testo, fonti:[S1,..], natura}]
  divergences         text not null default '',
  terms               text[] not null default '{}',
  relevance           int not null default 3 check (relevance between 1 and 5),
  is_must_read        boolean not null default false,
  verification_level  text not null
                      check (verification_level in ('fonte_primaria','confermata','fonte_singola','non_confermata')),
  verification_notes  jsonb not null default '[]'::jsonb,
  event_date          date,
  model_used          text,
  created_at          timestamptz not null default now(),
  search              tsvector generated always as (
                        to_tsvector('italian'::regconfig, coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(context,''))
                      ) stored
);
create index if not exists stories_edition_idx on public.stories (edition_date desc);
create index if not exists stories_category_idx on public.stories (category_slug, edition_date desc);
create index if not exists stories_thread_idx on public.stories (thread_id);
create index if not exists stories_search_idx on public.stories using gin (search);

create table if not exists public.story_sources (
  id               uuid primary key default gen_random_uuid(),
  story_id         uuid not null references public.stories(id) on delete cascade,
  ref              text not null,                          -- S1, S2, …
  source_name      text not null,
  title            text not null default '',
  url              text not null,
  published_at     timestamptz,
  is_primary       boolean not null default false,
  fulltext_used    boolean not null default false
);
create index if not exists story_sources_story_idx on public.story_sources (story_id);

-- ---------------------------------------------------------------------
-- Glossario
-- ---------------------------------------------------------------------
create table if not exists public.glossary (
  id                 uuid primary key default gen_random_uuid(),
  slug               text not null unique,
  term               text not null,
  aliases            text[] not null default '{}',
  simple_definition  text not null,
  explanation        text not null default '',
  example            text not null default '',
  related            text[] not null default '{}',          -- slug di voci collegate
  origin             text not null default 'curata' check (origin in ('curata','generata')),
  reviewed           boolean not null default true,         -- per le generate: superato il ricontrollo
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create table if not exists public.glossary_story_links (
  glossary_id  uuid not null references public.glossary(id) on delete cascade,
  story_id     uuid not null references public.stories(id) on delete cascade,
  primary key (glossary_id, story_id)
);

-- ---------------------------------------------------------------------
-- Stato di lettura (salvate / lette)
-- ---------------------------------------------------------------------
create table if not exists public.user_story_state (
  story_id   uuid primary key references public.stories(id) on delete cascade,
  saved      boolean not null default false,
  saved_at   timestamptz,
  read_at    timestamptz
);

-- =====================================================================
-- Sicurezza: solo il proprietario (email in settings) può leggere.
-- La pipeline usa la chiave service_role, che non è soggetta a RLS.
-- =====================================================================
create or replace function public.is_owner()
returns boolean
language sql stable security definer
set search_path = public
as $$
  select coalesce(
    (select lower(owner_email) from public.settings where id = 1) = lower(auth.jwt() ->> 'email'),
    false
  );
$$;

do $$
declare t text;
begin
  foreach t in array array['settings','categories','sources','runs','editions','stories',
                           'story_sources','glossary','glossary_story_links','user_story_state']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists owner_read on public.%I', t);
    execute format('create policy owner_read on public.%I for select to authenticated using (public.is_owner())', t);
  end loop;

  -- Tabelle che il proprietario può modificare dal sito
  foreach t in array array['settings','categories','sources','user_story_state']
  loop
    execute format('drop policy if exists owner_write on public.%I', t);
    execute format('create policy owner_write on public.%I for all to authenticated using (public.is_owner()) with check (public.is_owner())', t);
  end loop;
end $$;

-- Nessun accesso per utenti non autenticati
revoke all on all tables in schema public from anon;
