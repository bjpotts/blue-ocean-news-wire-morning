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

## License

Private — for Blue Ocean Equities Pty Ltd internal use.
