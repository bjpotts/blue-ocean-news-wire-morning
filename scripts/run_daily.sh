#!/bin/bash
# Market Wrap Up Morning Edition scheduled run - Monday to Saturday 08:00 (Australia/Sydney).
# Rebuilds the digest, produces the full PDF, then emails the full PDF.
set -euo pipefail

PROJ="/Users/brandonpotts/.verdent/verdent-projects/run-the-public-news-morning"
LOG="$PROJ/scheduler.log"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
# This project's identity is the Morning Edition regardless of what the wall
# clock says. build.py otherwise falls back to auto-detecting am/pm from the
# Sydney clock, which is only correct if this script happens to run inside
# its scheduled 08:00 window -- a manual/out-of-window run would mislabel
# the masthead and PDF filename as the Evening Edition instead.
export EDITION_OVERRIDE="Morning Edition"

cd "$PROJ"
{
  echo "===== RUN $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
  # Refresh live data first. A fetch failure must not abort the run: each
  # fetcher leaves the previous file in place, and build.py's freshness guard
  # is what decides whether the resulting data is too stale to publish.
  python3 fetch_markets.py || echo "WARN: fetch_markets.py failed"
  python3 fetch_commodities.py || echo "WARN: fetch_commodities.py failed"
  python3 fetch_performers.py || echo "WARN: fetch_performers.py failed"
  python3 fetch_capraises.py || echo "WARN: fetch_capraises.py failed"
  python3 fetch_tech.py || echo "WARN: fetch_tech.py failed"
  python3 fetch_news.py || echo "WARN: fetch_news.py failed"
  python3 fetch_sport.py || echo "WARN: fetch_sport.py failed"
  python3 fetch_weather.py || echo "WARN: fetch_weather.py failed"
  python3 fetch_guardian.py || echo "WARN: fetch_guardian.py failed"
  python3 build.py
  python3 make_snapshot.py
  python3 make_pdf.py
  RUN_ID="$(date '+%Y-%m-%d')-am"
  python3 /Users/brandonpotts/.verdent/verdent-projects/market-wrap-up-data/ingest.py \
    --project "$PROJ" \
    --run-id "$RUN_ID" \
    --edition "Morning Edition"
  # Mirror the run into Supabase so the published report and comparison
  # view can read history from the cloud database. Sync this run by id
  # rather than letting the default "only what is missing" mode decide:
  # a rebuild of a run_id that already exists must overwrite it, otherwise
  # a re-run silently leaves the cloud copy on the earlier build's data.
  # Non-fatal, since the local SQLite store stays the source of truth.
  python3 sync_supabase.py --run-id "$RUN_ID" || echo "WARN: sync_supabase.py failed"
  python3 /Users/brandonpotts/.verdent/verdent-projects/market-wrap-up-data/compare.py
  python3 "$PROJ/scripts/send_email.py"
  echo "===== DONE $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
} >> "$LOG" 2>&1
