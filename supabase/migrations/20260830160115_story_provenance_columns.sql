alter table public.news add column if not exists source_url text;
alter table public.news add column if not exists published_at timestamptz;
alter table public.news add column if not exists fetched_at timestamptz;

alter table public.capital_raises add column if not exists source_url text;
alter table public.capital_raises add column if not exists published_at timestamptz;
alter table public.capital_raises add column if not exists fetched_at timestamptz;

create index if not exists idx_news_source_url on public.news(source_url);
create index if not exists idx_news_published_at on public.news(published_at);