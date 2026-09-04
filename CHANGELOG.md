# Changelog

Notable changes to the Market Wrap Up **Morning Edition** project.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are
Australia/Sydney, matching the digest's own schedule. Entries begin 2026-08-31.

## [2026-09-05]

### Added

- A Market Earnings Reporting section, sitting between Top Performers and Capital Raises &
  New Listings. One region block per Top Performers region (ANZ, Asia, US, UK, Europe,
  Rest), each with a freshly-written summary paragraph and a headline list of genuine,
  linked corporate earnings/results/guidance stories from real business-news feeds
  (Stockhead, Small Caps, The Market Herald for ANZ; SCMP for Asia; Nasdaq and CNBC for
  the US; City A.M. for the UK; Bloomberg and Investing.com for Europe and the rest of the
  world). Reuses the same fresh-over-repeat rotation and honest-empty-region rules as
  Capital Raises, and the identical `cr-grid`/`cr-region` visual pattern, so no new CSS
  was needed. A region with nothing verifiable from a linked source says so plainly rather
  than being padded.

## [2026-09-04]

### Changed

- World Indices grid restored to its full 24 cells. The narrowing to 9 (below) is reverted:
  Dow Jones, Russell 2000, FTSE 250 and FTSE 350 move back to narrative-only fetching, and
  the 11 previously-dropped benchmarks (TSX Composite, IPC Mexico, FTSE MIB, IBEX 35, Euro
  Stoxx 50, OMX Stockholm 30, MOEX Russia, DFM General, TAIEX, SET Index, NZX 50) are fetched
  and shown again. The Google Finance links added for FTSE 250/350 are removed along with
  them, since those two are narrative-only again and no longer need a grid-cell link.

## [2026-09-03]

### Changed

- World Indices grid narrowed from 24 cells to the 9 you asked for: Dow Jones, S&P 500,
  Nasdaq Composite, Russell 2000, S&P/ASX 200, All Ordinaries, FTSE 100, FTSE 250 and
  FTSE 350. The 11 indices no longer required by name (TSX, IPC Mexico, FTSE MIB, IBEX 35,
  Euro Stoxx 50, OMX Stockholm 30, MOEX Russia, DFM General, TAIEX, SET Index, NZX 50) are
  dropped entirely; DAX, CAC 40, Hang Seng, Nikkei 225, KOSPI, Shanghai Composite, Ibovespa,
  Straits Times and BSE Sensex move to narrative-only fetching so the Market News paragraph
  can still cite them per its own "genuinely broad world coverage" brief, without taking a
  grid cell. FTSE 250/350 have no working Yahoo Finance quote page (confirmed 404), so both
  link to Google Finance instead, verified live before wiring in.

### Fixed

- The Capital Raises & New Listings summary paragraph for ANZ, UK and Rest was permanently
  pinned to one hand-written paragraph from `data/backfill.json`, dated 26 August. Every
  build overwrote that run's freshly generated summary with the same fixed text, so the
  paragraph never changed no matter how many times the report ran — and for Rest it had
  drifted out of sync with the (now empty) item list, describing Indian IPO activity
  directly above a line saying no items were found. `build.py` no longer reads a backfilled
  summary; `fetch_capraises.py`'s own per-run summary is used every time.
- A region's Capital Raises items could also resurface the exact same headline run after
  run whenever nothing fresher happened to be published in the fetch window. Item selection
  now prefers anything not shown in the previous run over a repeat, and the summary says so
  plainly ("no newer item since the last edition") on the runs where a repeat is genuinely
  unavoidable rather than implying fresh activity.

### Added

- The Market Herald as a third ANZ Capital Raises source, widening the pool of candidate
  headlines behind the rotation above.

## [2026-09-02]

### Added

- A test suite covering the pipeline end to end: 229 tests over feed parsing, the shared
  news lookup, market and commodity fetching, performer scraping, the build helpers and the
  delivery step. No network access — every fetcher runs against injected feeds and stubbed
  HTTP — so the suite completes offline in well under a second. Run it with `./run_tests.sh`.
- Whole-page invariants in `tests/test_integrity.py`, enforcing the standing rules rather
  than unit behaviour: every data point resolves to a working link, the rate and index grids
  hold 24 cells, gainers and losers point the right way, and no section carries prose that
  has stopped tracking the data. It reads the last build and skips when none exists.

### Fixed

- Atom feeds using single-quoted `href` attributes parsed as empty. Valid XML, but the link
  pattern matched double quotes only, so such a feed produced no headlines rather than an
  error.
- A change rendered with a Unicode minus was coloured as unchanged instead of a loss.
  TradingView writes U+2212, not a hyphen, so the value reached the page uncoloured.

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
