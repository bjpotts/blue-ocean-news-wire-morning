#!/bin/bash
# Market Wrap Up Morning Edition scheduled run - Monday to Saturday 08:00 (Australia/Sydney).
# Rebuilds the digest, produces the full PDF, then emails the full PDF.
# Retries the fetch+build sequence up to 3 times if build.py rejects stale data.
# If all retries fail, sends a failure email explaining the problem.
set -uo pipefail

PROJ="/Users/brandonpotts/.verdent/verdent-projects/run-the-public-news-morning"
LOG="$PROJ/scheduler.log"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
# Homebrew Python 3.14, when launched from launchctl's minimal environment,
# cannot verify TLS certificates without an explicit CA bundle. Point urllib
# and requests at the certifi bundle so every HTTPS data fetch succeeds.
export SSL_CERT_FILE="$(python3 -c 'import certifi; print(certifi.where())')"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
# This project's identity is the Morning Edition regardless of what the wall
# clock says. build.py otherwise falls back to auto-detecting am/pm from the
# Sydney clock, which is only correct if this script happens to run inside
# its scheduled 08:00 window -- a manual/out-of-window run would mislabel
# the masthead and PDF filename as the Evening Edition instead.
export EDITION_OVERRIDE="Morning Edition"
EDITION="Morning Edition"

FETCHERS=(
  fetch_markets.py
  fetch_commodities.py
  fetch_performers.py
  fetch_capraises.py
  fetch_earnings.py
  fetch_tech.py
  fetch_news.py
  fetch_sport.py
  fetch_weather.py
  fetch_guardian.py
)

cd "$PROJ"

fetch_all() {
  # Refresh live data. A fetch failure must not abort the run: each
  # fetcher leaves the previous file in place, and build.py's freshness guard
  # is what decides whether the resulting data is too stale to publish.
  for f in "${FETCHERS[@]}"; do
    python3 "$f" || echo "WARN: $f failed"
  done
}

build_artifacts() {
  python3 build.py
  python3 make_snapshot.py
  python3 make_pdf.py
}

publish_run() {
  RUN_ID="$(date '+%Y-%m-%d')-am"
  python3 /Users/brandonpotts/.verdent/verdent-projects/market-wrap-up-data/ingest.py \
    --project "$PROJ" \
    --run-id "$RUN_ID" \
    --edition "$EDITION"
  # Mirror the run into Supabase so the published report and comparison
  # view can read history from the cloud database. Sync this run by id
  # rather than letting the default "only what is missing" mode decide:
  # a rebuild of a run_id that already exists must overwrite it, otherwise
  # a re-run silently leaves the cloud copy on the earlier build's data.
  # Non-fatal, since the local SQLite store stays the source of truth.
  python3 sync_supabase.py --run-id "$RUN_ID" || echo "WARN: sync_supabase.py failed"
  python3 /Users/brandonpotts/.verdent/verdent-projects/market-wrap-up-data/compare.py
  python3 "$PROJ/scripts/send_email.py"
}

send_failure() {
  local reason="$1"
  python3 "$PROJ/scripts/send_failure_email.py" --edition "$EDITION" --reason "$reason" || \
    echo "WARN: send_failure_email.py failed"
}

{
  echo "===== RUN $(date '+%Y-%m-%d %H:%M:%S %Z') ====="

  MAX_RETRIES=3
  ATTEMPT=1
  FAIL_REASON=""

  while [ "$ATTEMPT" -le "$MAX_RETRIES" ]; do
    echo "--- attempt $ATTEMPT/$MAX_RETRIES ---"
    fetch_all

    BUILD_OUT="$(mktemp)"
    if build_artifacts > "$BUILD_OUT" 2>&1; then
      echo "build succeeded on attempt $ATTEMPT"
      rm -f "$BUILD_OUT"
      publish_run
      echo "===== DONE $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
      exit 0
    fi

    FAIL_REASON="$(cat "$BUILD_OUT")"
    rm -f "$BUILD_OUT"
    echo "ERROR on attempt $ATTEMPT:"
    echo "$FAIL_REASON"

    if [ "$ATTEMPT" -lt "$MAX_RETRIES" ]; then
      BACKOFF=$((60 * ATTEMPT))
      echo "retrying in ${BACKOFF}s..."
      sleep "$BACKOFF"
    fi
    ATTEMPT=$((ATTEMPT + 1))
  done

  echo "ERROR: all $MAX_RETRIES attempts failed"
  echo "$FAIL_REASON"
  send_failure "$FAIL_REASON"
  echo "===== FAILED $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
  exit 1
} >> "$LOG" 2>&1
