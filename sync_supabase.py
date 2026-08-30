#!/usr/bin/env python3
"""Push digest run history from the local SQLite store into Supabase.

The daily pipeline writes each run to market-history.db first; this mirrors
those rows into Supabase so the published report and the comparison view can
read history from the cloud database.

Writes go through the ingest_digest() RPC rather than direct table inserts.
The anon key is browser-visible, so it deliberately has read-only access to the
content tables; the RPC is gated by SUPABASE_INGEST_SECRET from .env.local.

Usage:
  python3 sync_supabase.py                # sync runs missing from Supabase
  python3 sync_supabase.py --run-id ID    # sync one run
  python3 sync_supabase.py --all          # re-sync every local run
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "..", "market-wrap-up-data", "market-history.db")

TABLES = {
    "market_data": ["kind", "symbol", "value", "unit", "chg_pct", "note", "url"],
    "performers": ["region", "side", "ticker", "name", "price", "chg_pct",
                   "volume", "url"],
    "capital_raises": ["region", "headline", "detail", "outlet", "url"],
    "news": ["section", "outlet", "code", "headline", "detail", "url"],
    "weather": ["place", "condition", "temp", "feels", "humidity", "wind",
                "high", "low", "rain_chance"],
}
NUMERIC = {"value", "chg_pct", "price", "volume", "temp", "feels", "high", "low"}


def load_env():
    path = os.path.join(HERE, ".env.local")
    if not os.path.exists(path):
        sys.exit("ERROR: .env.local not found; cannot reach Supabase.")
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    missing = [k for k in ("VITE_SUPABASE_URL", "VITE_SUPABASE_PUBLISHABLE_KEY",
                           "SUPABASE_INGEST_SECRET") if not env.get(k)]
    if missing:
        sys.exit("ERROR: .env.local is missing: %s" % ", ".join(missing))
    return env


def post(env, path, payload, timeout=120):
    req = urllib.request.Request(
        env["VITE_SUPABASE_URL"].rstrip("/") + path,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "apikey": env["VITE_SUPABASE_PUBLISHABLE_KEY"],
            "Authorization": "Bearer " + env["VITE_SUPABASE_PUBLISHABLE_KEY"],
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
    return json.loads(body) if body else None


def get(env, path, timeout=60):
    req = urllib.request.Request(
        env["VITE_SUPABASE_URL"].rstrip("/") + path,
        headers={
            "apikey": env["VITE_SUPABASE_PUBLISHABLE_KEY"],
            "Authorization": "Bearer " + env["VITE_SUPABASE_PUBLISHABLE_KEY"],
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def collect(con, run_id):
    rows = {}
    for table, cols in TABLES.items():
        out = []
        for r in con.execute("select %s from %s where run_id=?" % (",".join(cols), table),
                             (run_id,)):
            item = {}
            for col, val in zip(cols, r):
                item[col] = num(val) if col in NUMERIC else val
            out.append(item)
        rows[table] = out
    return rows


def sync_run(env, con, run):
    rows = collect(con, run["run_id"])
    payload = {
        "p_secret": env["SUPABASE_INGEST_SECRET"],
        "p_run": {
            "run_id": run["run_id"],
            "edition": run["edition"],
            "edition_date": run["date"],
            "market_summary": run["market_summary"],
            "as_of": run["created_at"],
            "created_at": run["created_at"],
        },
        "p_rows": rows,
    }
    result = post(env, "/rest/v1/rpc/ingest_digest", payload)
    counts = (result or {}).get("counts", {})
    print("  %-16s %s" % (run["run_id"],
                          " ".join("%s=%s" % (k, counts[k]) for k in sorted(counts))))
    return sum(counts.values())


def market_summary_for(run_id):
    """The Market News paragraph is not kept in SQLite; read it from the run's
    data directory when the run being synced is the one on disk."""
    try:
        pc = json.load(open(os.path.join(HERE, "data", "perf-c.json")))
        return (pc.get("market_news") or {}).get("paragraph")
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    env = load_env()
    if not os.path.exists(DB):
        sys.exit("ERROR: local history database not found at %s" % DB)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    local = [dict(r) for r in con.execute("select * from runs order by run_id")]
    if args.run_id:
        wanted = [r for r in local if r["run_id"] == args.run_id]
        if not wanted:
            sys.exit("ERROR: run %s is not in the local history" % args.run_id)
    elif args.all:
        wanted = local
    else:
        try:
            remote = {r["run_id"] for r in get(env, "/rest/v1/digest_runs?select=run_id")}
        except urllib.error.HTTPError as exc:
            sys.exit("ERROR: could not read Supabase: %s %s"
                     % (exc.code, exc.read().decode()[:200]))
        wanted = [r for r in local if r["run_id"] not in remote]

    if not wanted:
        print("Supabase is already up to date (%d runs)." % len(local))
        return 0

    print("syncing %d run(s) to Supabase" % len(wanted))
    total = 0
    failed = []
    for run in wanted:
        run["market_summary"] = market_summary_for(run["run_id"])
        try:
            total += sync_run(env, con, run)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:200]
            print("  ! %s failed: %s %s" % (run["run_id"], exc.code, detail),
                  file=sys.stderr)
            failed.append(run["run_id"])
        except Exception as exc:
            print("  ! %s failed: %s" % (run["run_id"], exc), file=sys.stderr)
            failed.append(run["run_id"])

    print("synced %d rows across %d run(s)" % (total, len(wanted) - len(failed)))
    if failed:
        print("FAILED: %s" % ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
