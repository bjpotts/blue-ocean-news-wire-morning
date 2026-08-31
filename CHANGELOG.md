# Changelog

Notable changes to the Market Wrap Up **Morning Edition** project.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are
Australia/Sydney, matching the digest's own schedule. Entries begin 2026-08-31.

## [2026-08-31]

### Added

- Eight more benchmarks in World Indices, taking the grid to 24 — six rows of four, matching
  Exchange Rates & Bitcoin and ordered west to east so each row reads as a region. Covers
  New York, London, Frankfurt, Paris, India, both Australian benchmarks, the Asian markets
  and Dubai for the UAE.
- Eight more commodities, taking that grid to 24 as well: Brent Crude, zinc, lead and tin to
  complete the LME base metals, and a grains and softs row of wheat, corn, soybeans and
  sugar. Agriculture had been absent entirely, and Brent was named in the Market News copy
  without appearing in the grid.
- Supabase ingest, through a `SECURITY DEFINER` RPC gated by a secret in a gitignored
  `.env.local`, so the browser-visible anon key stays read-only.
- A discovery record for every story: source URL, published timestamp, fetched timestamp.
- A `story_archive` view in Supabase, exposing a rolling 30-day window of every story and
  capital raise for the app to query. Folded on the story's link, so a headline that ran in
  several editions is one row carrying the span and the edition count.
- `EDITION_OVERRIDE`, for running an edition outside its scheduled window.
- A staleness guard on index quotes: flagged in the grid after a week, dropped after a month.

### Changed

- Every data-driven section now fetches live each run, including the Market News paragraph
  and all gainers and losers regions, which could previously carry over.
- MOEX Russia now comes from the Moscow Exchange API. Yahoo's IMOEX series froze in July
  2022 and would have published a four-year-old level as the day's close.
- All sections are now config-driven through `data/config.json`.

### Fixed

- The daily Supabase sync skipped rebuilt runs, leaving the cloud copy on the previous
  build's data, because its default mode pushes only run ids that are missing. It now targets
  its own run explicitly.
- The Market News paragraph could be attached to both editions at once, as a time-window
  match cannot separate two builds minutes apart. It now resolves to a single run.
- Indices on thinly-covered exchanges reported `+0.00%`, having only one daily close to
  compare against. They now fall back to the chart's previous close.
- NZX 50 linked to a Yahoo US page that 404s. All three Australasian indices now use Yahoo's
  AU edition.
- A failed commodity fetch published an invented `0.00` price. The cell is dropped instead.
- Proxy and stale chips rendered clipped on longer labels. The label row now wraps rather
  than forcing two non-wrapping spans through a fixed-width cell.
- The commodities fetcher called Kitco twice per precious metal, the second time only to
  record which source had answered. It now records that from the first.
