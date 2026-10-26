#!/usr/bin/env python3
"""Compare the latest digest run against the previous same-edition run.

If market data and performer rosters are effectively unchanged, send a warning
email so the stale run is noticed. This catches fetchers that crash silently or
sources that return cached data.
"""
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
DB = os.path.join(PROJ, "..", "market-wrap-up-data", "market-history.db")

TO = "bjpotts@gmail.com"
FROM = "bjpotts@gmail.com"
SUBJECT = "Market Wrap Up - DATA UNCHANGED WARNING"


def ensure_mail_running():
    out = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to return (name of processes) contains "Mail"'],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if out != "true":
        subprocess.run(["open", "-a", "Mail"], check=False)
        import time
        time.sleep(3)


def send_alert(edition, run_id, prev_id, reasons, dry_run=False):
    body = """The %s run (%s) appears to carry unchanged data from the previous run (%s).

Issues detected:
%s

Please check that the fetchers are running and the data sources are returning fresh values.

Regards

Market Wrap Up Scheduler""" % (edition, run_id, prev_id, "\n".join("- " + r for r in reasons))

    if dry_run:
        print("DRY RUN: would send freshness alert for %s" % run_id)
        print(body)
        return True

    ensure_mail_running()
    script = '''
tell application "Mail"
    set theMessage to make new outgoing message with properties {visible:false}
    tell theMessage
        set subject to "%s"
        set content to "%s"
        make new to recipient at end of to recipients with properties {address:"%s"}
        set sender to "%s"
        save theMessage
        delay 2
        send theMessage
    end tell
end tell
''' % (SUBJECT, body, TO, FROM)

    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        print("FRESHNESS EMAIL ERROR: %s" % result.stderr.strip(), file=sys.stderr)
        return False
    print("FRESHNESS ALERT SENT: %s vs %s" % (run_id, prev_id))
    return True


def market_data_signature(con, run_id):
    rows = con.execute(
        "select kind, symbol, value, chg_pct from market_data where run_id=? order by kind, symbol",
        (run_id,),
    ).fetchall()
    return set((k, s, v, c) for k, s, v, c in rows)


def performer_tickers(con, run_id):
    rows = con.execute(
        "select distinct region, side, ticker from performers where run_id=? order by region, side, ticker",
        (run_id,),
    ).fetchall()
    return set(rows)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(DB):
        print("WARNING: history database not found at %s" % DB, file=sys.stderr)
        return 0

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    runs = con.execute(
        "select run_id, edition, date, created_at from runs order by created_at desc, run_id desc"
    ).fetchall()
    if len(runs) < 2:
        print("Not enough history to compare.")
        return 0

    latest = runs[0]
    prev = None
    for r in runs[1:]:
        if r["edition"] == latest["edition"]:
            prev = r
            break
    if not prev:
        print("No previous %s run to compare against." % latest["edition"])
        return 0

    latest_md = market_data_signature(con, latest["run_id"])
    prev_md = market_data_signature(con, prev["run_id"])
    latest_perf = performer_tickers(con, latest["run_id"])
    prev_perf = performer_tickers(con, prev["run_id"])

    reasons = []
    if latest_md == prev_md:
        reasons.append("Market data (indices/FX/commodities/BTC) is identical to the previous run.")
    if latest_perf == prev_perf:
        reasons.append("Top performer tickers are identical to the previous run.")

    if reasons:
        send_alert(latest["edition"], latest["run_id"], prev["run_id"], reasons, dry_run=args.dry_run)
        return 1

    print("Data changed since previous %s run (%s)." % (latest["edition"], prev["run_id"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
