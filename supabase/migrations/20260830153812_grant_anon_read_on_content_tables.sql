-- The initial schema enabled RLS and created public-read policies, but never
-- granted table privileges to the anon role. PostgREST requires both a GRANT
-- and an RLS policy, so anon reads failed with 42501 permission denied and the
-- report page could not read any published digest content.
-- saved_items is intentionally excluded: it is user-owned and stays restricted
-- to the authenticated role via its own auth.uid() policies.

grant usage on schema public to anon;

grant select on public.digest_runs    to anon;
grant select on public.market_data    to anon;
grant select on public.performers     to anon;
grant select on public.capital_raises to anon;
grant select on public.news           to anon;
grant select on public.weather        to anon;