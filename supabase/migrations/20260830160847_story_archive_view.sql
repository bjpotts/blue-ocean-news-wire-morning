-- Rolling one-month archive of every story link, folded so a headline that ran
-- in several editions is one row carrying the span and the number of editions.
-- security_invoker keeps the caller's RLS in force rather than the view owner's.
create or replace view public.story_archive
with (security_invoker = true) as
select
  n.section,
  n.outlet          as source,
  n.headline,
  n.url,
  n.source_url,
  min(r.edition_date) as first_seen,
  max(r.edition_date) as last_seen,
  count(distinct n.run_id)::int as editions,
  min(n.published_at) as published_at
from public.news n
join public.digest_runs r on r.run_id = n.run_id
where r.edition_date >= (current_date - interval '30 days')
group by n.section, n.outlet, n.headline, n.url, n.source_url

union all

select
  'capital raises' as section,
  c.region         as source,
  c.headline,
  c.url,
  c.source_url,
  min(r.edition_date),
  max(r.edition_date),
  count(distinct c.run_id)::int,
  min(c.published_at)
from public.capital_raises c
join public.digest_runs r on r.run_id = c.run_id
where r.edition_date >= (current_date - interval '30 days')
group by c.region, c.headline, c.url, c.source_url;

grant select on public.story_archive to anon, authenticated;