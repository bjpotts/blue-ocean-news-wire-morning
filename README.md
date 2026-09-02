# Market Wrap Up — Morning Edition

A pure market wrap-up digest for **Blue Ocean Equities Pty Ltd** (boeq.com.au), an independent Australian securities/equities advisory firm.

This is the **Morning Edition**, scheduled to run Monday–Saturday at 8:00 AM Australia/Sydney time.

## What it does

Generates a self-contained HTML digest covering:

- Global market summary
- Exchange rates & Bitcoin
- World indices
- Commodities
- Top performers (gainers/losers) across ANZ, Asia, US, UK, Europe, and Brazil
- Capital raises & new listings
- Technology news
- World news from major outlets
- World sport

Every data point is a clickable link to a real, working source URL.

## Branding

- Headings: **Libre Franklin**
- Body: **Source Sans 3**
- Dateline/labels/tables: **IBM Plex Mono**
- Primary: **Cerulean #00A0D2**
- Accent: **Viking #67CCE0**
- Headers: **Pine Green #006F6F**

## Tech stack

- [Vite](https://vitejs.dev/) — build tooling
- [Supabase](https://supabase.com/) — backend database (schema in `supabase/migrations/`)
- [@verdent/auth-js](https://www.npmjs.com/package/@verdent/auth-js) — auth integration (UI currently hidden)
- Python scripts in the project root for data fetching and PDF generation

## Run locally

```bash
npm install
npm run dev
```

Build for production:

```bash
npm run build
```

## Data pipeline

Scheduled runs execute `scripts/run_daily.sh`, which fetches fresh data and rebuilds the digest. The resulting `digest.html` is loaded dynamically by the frontend.

## Tests

```bash
./run_tests.sh        # quiet
./run_tests.sh -v     # per-test names
```

229 tests, no network access — every fetcher is exercised through injected feeds and stubbed HTTP, so the suite runs offline in well under a second.

| Module | Covers |
| --- | --- |
| `test_feedlib.py` | RSS/Atom parsing, date formats, recency, dedupe, snippet trimming |
| `test_newsfeed.py` | The shared Google News lookup and its noise rules |
| `test_markets.py` | FX/index formatting, day-over-day change, the stale/drop guards |
| `test_commodities.py` | Per-family summary prose, stale flagging, the rare-earths proxy |
| `test_performers.py` | Screener scraping, row shaping, mover explainers, catalyst matching |
| `test_build.py` | Escaping, grid/table rendering, the data-freshness guards |
| `test_outputs.py` | PDF naming, email attachment choice, capital-raise summaries |
| `test_integrity.py` | Whole-page invariants against the last build |

`test_integrity.py` enforces the standing rules for the page rather than unit behaviour: every data point is a working link, the rate and index grids are 24 cells, no section carries frozen placeholder prose, and gainers/losers point the right way. It reads `public/digest.html` and skips cleanly when the page has not been built.

`build.py` is a script — importing it runs its guards and overwrites the digest — so `tests/helpers.py` lifts its pure helpers out of the source with `ast` instead of importing it.

## Changelog

Notable changes are recorded in [`CHANGELOG.md`](CHANGELOG.md).

## License

Private — for Blue Ocean Equities Pty Ltd internal use.
