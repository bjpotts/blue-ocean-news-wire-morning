# Changelog

Notable changes to the Market Wrap Up **Morning Edition** project.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are
Australia/Sydney, matching the digest's own schedule. Entries begin 2026-08-31.

## [2026-08-31]

### Added

- **World Indices grid widened from 16 to 24 benchmarks**, matching the Exchange Rates &
  Bitcoin grid at six rows of four. Ordered west to east so each row reads as a region, and
  covering NYC, London, Frankfurt, France, India, both Australian benchmarks, the Asian
  markets and Dubai for the UAE.
- **Commodities grid widened from 16 to 24.** Adds Brent Crude, which the Market News copy
  already referenced without it appearing in the grid; completes the LME base-metals complex
  with zinc, lead and tin; and adds a grains and softs row of wheat, corn, soybeans and
  sugar, as agriculture was absent entirely.
- Supabase linked into the pipeline. Writes go through a `SECURITY DEFINER` RPC gated by a
  secret held in a gitignored `.env.local`, so the browser-visible anon key keeps read-only
  access to the content tables.
- A discovery record for every story — source URL, published timestamp and fetched timestamp
  — carried through to Supabase.
- `EDITION_OVERRIDE` for running an edition manually outside its scheduled window.
- A staleness guard on index quotes: older than a week is flagged in the grid, older than a
  month is dropped rather than published.

### Changed

- Every data-driven section now fetches live on each run, including the Market News opening
  paragraph and all gainers and losers regions, which could previously carry over.
- MOEX Russia is sourced from the Moscow Exchange API rather than Yahoo, whose IMOEX series
  froze in July 2022 and would have published a four-year-old level as the day's close.
- All sections are config-driven through `data/config.json`.

### Fixed

- The daily Supabase sync now targets its own run explicitly. The default "push only what is
  missing" mode skipped a rebuilt run, because its id already existed remotely, silently
  leaving the cloud copy on the earlier build's data.
- The Market News paragraph is attached to the run it actually belongs to. Both editions can
  build minutes apart, and a time-window match had been assigning one paragraph to both.
- Indices on thinly-covered exchanges return a single daily close, which rendered as a
  misleading `+0.00%` change. They now fall back to the chart's own previous close.
- The NZX 50 quote link pointed at a Yahoo US page that returns 404. All three Australasian
  indices now route to Yahoo's AU edition.
- A failed commodity fetch fell back to a `0.00` placeholder, publishing an invented price.
  The cell is now dropped instead.
- The proxy and stale chips on rate cells rendered clipped once a label was long enough. The
  label row now wraps rather than forcing two non-wrapping spans through a fixed-width cell.
- The commodities fetcher called Kitco twice for every precious metal, once for data and
  again only to record which source had answered.
