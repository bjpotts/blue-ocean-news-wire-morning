-- Carry the story discovery record (source feed, published time, fetch time)
-- through the ingest path so provenance survives the trip into Supabase.

create or replace function public.ingest_digest(
  p_secret  text,
  p_run     jsonb,
  p_rows    jsonb
) returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_hash text;
  v_run_id text := p_run->>'run_id';
  v_counts jsonb := '{}'::jsonb;
  v_n int;
begin
  select secret_hash into v_hash from public.ingest_credentials where id = 1;
  if v_hash is null then
    raise exception 'ingest is not configured';
  end if;
  if p_secret is null
     or encode(extensions.digest(p_secret, 'sha256'), 'hex') <> v_hash then
    raise exception 'invalid ingest secret';
  end if;
  if v_run_id is null or length(v_run_id) = 0 then
    raise exception 'run_id is required';
  end if;

  insert into public.digest_runs (run_id, edition, edition_date, market_summary, as_of, created_at)
  values (
    v_run_id,
    p_run->>'edition',
    nullif(p_run->>'edition_date','')::date,
    p_run->>'market_summary',
    coalesce(nullif(p_run->>'as_of','')::timestamptz, now()),
    coalesce(nullif(p_run->>'created_at','')::timestamptz, now())
  )
  on conflict (run_id) do update set
    edition        = excluded.edition,
    edition_date   = excluded.edition_date,
    market_summary = excluded.market_summary,
    as_of          = excluded.as_of;

  delete from public.market_data    where run_id = v_run_id;
  delete from public.performers     where run_id = v_run_id;
  delete from public.capital_raises where run_id = v_run_id;
  delete from public.news           where run_id = v_run_id;
  delete from public.weather        where run_id = v_run_id;

  insert into public.market_data (run_id, kind, symbol, value, unit, chg_pct, note, url)
  select v_run_id, x.kind, x.symbol, x.value, x.unit, x.chg_pct, x.note, x.url
  from jsonb_to_recordset(coalesce(p_rows->'market_data','[]'::jsonb))
    as x(kind text, symbol text, value numeric, unit text, chg_pct numeric, note text, url text);
  get diagnostics v_n = row_count; v_counts := v_counts || jsonb_build_object('market_data', v_n);

  insert into public.performers (run_id, region, side, ticker, name, price, chg_pct, volume, url)
  select v_run_id, x.region, x.side, x.ticker, x.name, x.price, x.chg_pct, x.volume, x.url
  from jsonb_to_recordset(coalesce(p_rows->'performers','[]'::jsonb))
    as x(region text, side text, ticker text, name text, price numeric, chg_pct numeric, volume numeric, url text);
  get diagnostics v_n = row_count; v_counts := v_counts || jsonb_build_object('performers', v_n);

  insert into public.capital_raises (run_id, region, headline, detail, outlet, url, source_url, published_at, fetched_at)
  select v_run_id, x.region, x.headline, x.detail, x.outlet, x.url, x.source_url, x.published_at, x.fetched_at
  from jsonb_to_recordset(coalesce(p_rows->'capital_raises','[]'::jsonb))
    as x(region text, headline text, detail text, outlet text, url text,
         source_url text, published_at timestamptz, fetched_at timestamptz);
  get diagnostics v_n = row_count; v_counts := v_counts || jsonb_build_object('capital_raises', v_n);

  insert into public.news (run_id, section, outlet, code, headline, detail, url, source_url, published_at, fetched_at)
  select v_run_id, x.section, x.outlet, x.code, x.headline, x.detail, x.url, x.source_url, x.published_at, x.fetched_at
  from jsonb_to_recordset(coalesce(p_rows->'news','[]'::jsonb))
    as x(section text, outlet text, code text, headline text, detail text, url text,
         source_url text, published_at timestamptz, fetched_at timestamptz);
  get diagnostics v_n = row_count; v_counts := v_counts || jsonb_build_object('news', v_n);

  insert into public.weather (run_id, place, condition, temp, feels, humidity, wind, high, low, rain_chance)
  select v_run_id, x.place, x.condition, x.temp, x.feels, x.humidity, x.wind, x.high, x.low, x.rain_chance
  from jsonb_to_recordset(coalesce(p_rows->'weather','[]'::jsonb))
    as x(place text, condition text, temp numeric, feels numeric, humidity text, wind text, high numeric, low numeric, rain_chance text);
  get diagnostics v_n = row_count; v_counts := v_counts || jsonb_build_object('weather', v_n);

  return jsonb_build_object('run_id', v_run_id, 'counts', v_counts);
end;
$$;

revoke all on function public.ingest_digest(text, jsonb, jsonb) from public;
grant execute on function public.ingest_digest(text, jsonb, jsonb) to anon, authenticated;