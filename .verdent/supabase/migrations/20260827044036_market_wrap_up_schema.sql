-- Market Wrap Up data model
-- Content tables: one row-set per digest edition (run_id = e.g. 2026-08-27-pm).
-- saved_items: user-owned dynamic content, RLS enforced by auth.uid().

create table if not exists public.digest_runs (
  run_id          text primary key,
  edition         text not null,
  edition_date    date not null,
  market_summary  text,
  as_of           timestamptz,
  created_at      timestamptz not null default now()
);

create table if not exists public.market_data (
  id        bigint generated always as identity primary key,
  run_id    text not null references public.digest_runs(run_id) on delete cascade,
  kind      text not null check (kind in ('fx','index','commodity','btc')),
  symbol    text not null,
  value     numeric,
  unit      text,
  chg_pct   numeric,
  note      text,
  url       text,
  unique (run_id, kind, symbol)
);

create table if not exists public.performers (
  id      bigint generated always as identity primary key,
  run_id  text not null references public.digest_runs(run_id) on delete cascade,
  region  text not null,
  side    text not null check (side in ('gainer','loser')),
  ticker  text not null,
  name    text,
  price   numeric,
  chg_pct numeric,
  volume  numeric,
  url     text,
  unique (run_id, region, side, ticker)
);

create table if not exists public.capital_raises (
  id        bigint generated always as identity primary key,
  run_id    text not null references public.digest_runs(run_id) on delete cascade,
  region    text not null,
  headline  text not null,
  detail    text,
  outlet    text,
  url       text
);

create table if not exists public.news (
  id        bigint generated always as identity primary key,
  run_id    text not null references public.digest_runs(run_id) on delete cascade,
  section   text not null check (section in ('news','sport','tech')),
  outlet    text not null,
  code      text,
  headline  text not null,
  detail    text,
  url       text
);

create table if not exists public.weather (
  id          bigint generated always as identity primary key,
  run_id      text not null references public.digest_runs(run_id) on delete cascade,
  place       text not null,
  condition   text,
  temp        numeric,
  feels       numeric,
  humidity    text,
  wind        text,
  high        numeric,
  low         numeric,
  rain_chance text,
  unique (run_id, place)
);

create table if not exists public.saved_items (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  run_id      text references public.digest_runs(run_id) on delete set null,
  kind        text not null check (kind in ('news','sport','tech','capital_raise','performer')),
  title       text not null,
  outlet      text,
  detail      text,
  url         text,
  note        text,
  created_at  timestamptz not null default now()
);

create index if not exists idx_market_data_run on public.market_data(run_id);
create index if not exists idx_performers_run on public.performers(run_id);
create index if not exists idx_capital_raises_run on public.capital_raises(run_id);
create index if not exists idx_news_run on public.news(run_id);
create index if not exists idx_weather_run on public.weather(run_id);
create index if not exists idx_saved_items_user on public.saved_items(user_id);

-- RLS: digest content is public-read; writes only via service role (no policies).
alter table public.digest_runs enable row level security;
alter table public.market_data enable row level security;
alter table public.performers enable row level security;
alter table public.capital_raises enable row level security;
alter table public.news enable row level security;
alter table public.weather enable row level security;
alter table public.saved_items enable row level security;

create policy "digest_runs_public_read" on public.digest_runs
  for select using (true);
create policy "market_data_public_read" on public.market_data
  for select using (true);
create policy "performers_public_read" on public.performers
  for select using (true);
create policy "capital_raises_public_read" on public.capital_raises
  for select using (true);
create policy "news_public_read" on public.news
  for select using (true);
create policy "weather_public_read" on public.weather
  for select using (true);

-- saved_items is user-owned dynamic content: auth.uid() must match user_id.
create policy "saved_items_select_own" on public.saved_items
  for select using (auth.uid() = user_id);
create policy "saved_items_insert_own" on public.saved_items
  for insert with check (auth.uid() = user_id);
create policy "saved_items_update_own" on public.saved_items
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "saved_items_delete_own" on public.saved_items
  for delete using (auth.uid() = user_id);