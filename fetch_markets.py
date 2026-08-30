#!/usr/bin/env python3
"""Fetch fresh FX, Bitcoin and world-index data for the Market Wrap Up digest."""
import json, os, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(D, exist_ok=True)

SYD = ZoneInfo("Australia/Sydney")
UTC = ZoneInfo("UTC")

CURRENCY_CODES = [
    "AUD", "EUR", "GBP", "JPY", "CNY", "NZD", "CAD", "CHF", "SGD", "HKD",
    "INR", "KRW", "MXN", "BRL", "ZAR", "ILS", "SEK", "NOK", "THB", "MYR",
    "PHP", "IDR"
]

# The 20 indices shown in the World Indices grid, ordered west to east so the
# 4-column grid reads as five geographic rows: the Americas, Europe, then the
# Middle East into Asia, the rest of Asia, and finally India with ANZ.
INDICES = [
    ("S&P 500", "^GSPC"),
    ("Nasdaq Composite", "^IXIC"),
    ("TSX Composite", "^GSPTSE"),
    ("Ibovespa", "^BVSP"),
    ("FTSE 100", "^FTSE"),
    ("DAX", "^GDAXI"),
    ("CAC 40", "^FCHI"),
    ("FTSE MIB", "FTSEMIB.MI"),
    ("EURO STOXX 50", "^STOXX50E"),
    ("DFM General (Dubai)", "DFMGI.AE"),
    ("Nikkei 225", "^N225"),
    ("Hang Seng", "^HSI"),
    ("Shanghai Composite", "000001.SS"),
    ("KOSPI", "^KS11"),
    ("TAIEX", "^TWII"),
    ("SET Index", "^SET.BK"),
    ("BSE Sensex", "^BSESN"),
    ("S&P/ASX 200", "^AXJO"),
    ("All Ordinaries", "^AORD"),
    ("NZX 50", "^NZ50"),
]

# Indices the Market News paragraph talks about but the grid no longer shows.
# They are fetched so the written summary keeps its full regional coverage, and
# are kept out of "indices" so the displayed grid stays exactly 20 cells.
NARRATIVE_INDICES = [
    ("Dow Jones", "^DJI"),
    ("Russell 2000", "^RUT"),
    ("Straits Times", "^STI"),
]

# Yahoo keeps serving a "price" for indices it stopped tracking years ago, so a
# quote is only trusted while its timestamp is recent. Markets close over
# weekends and holidays, hence the week of slack before anything is flagged.
STALE_AFTER_DAYS = 7
DROP_AFTER_DAYS = 30


def _fmt(n):
    if n is None:
        return ""
    if n >= 10000:
        return f"{n:,.0f}"
    if n >= 1000:
        return f"{n:,.2f}"
    return f"{n:.4f}"


def _pct(prev, curr):
    if not prev or not curr or prev == 0:
        return "0.00%"
    v = (curr - prev) / prev * 100
    return f"{v:+.2f}%"


def fetch_fx():
    latest = requests.get("https://api.frankfurter.dev/v1/latest?from=USD", timeout=30).json()
    # Frankfurter publishes ECB business-day fixings, so "latest" on a weekend
    # or holiday returns an earlier date. Anchor the comparison on the date the
    # API actually returned, then walk back until we get a genuinely different
    # fixing, otherwise every cell reports a 0.00% change.
    base = latest.get("date") or datetime.now(UTC).strftime("%Y-%m-%d")
    base_dt = datetime.strptime(base, "%Y-%m-%d")

    prior_data, prior = None, None
    probe = base_dt - timedelta(days=1)
    for _ in range(7):
        while probe.weekday() >= 5:
            probe -= timedelta(days=1)
        candidate = requests.get(
            f"https://api.frankfurter.dev/v1/{probe:%Y-%m-%d}?from=USD", timeout=30).json()
        got = candidate.get("date")
        if got and got != base:
            prior_data, prior = candidate, got
            break
        probe -= timedelta(days=1)

    if prior_data is None:
        print("WARN: could not resolve a prior FX fixing date; changes will be zero",
              file=sys.stderr)
        prior_data, prior = latest, base

    rows = []
    for code in CURRENCY_CODES:
        rate = latest["rates"].get(code)
        prev = prior_data["rates"].get(code)
        if rate is None:
            continue
        rows.append({"code": code, "rate": f"{rate:.4f}", "chg": _pct(prev, rate)})
    return rows, base, prior


def fetch_btc():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
    data = requests.get(url, timeout=30).json()
    btc = data["bitcoin"]
    price = btc["usd"]
    chg = btc["usd_24h_change"]
    return {
        "price": f"${price:,.0f}",
        "chg": f"{chg:+.2f}%",
        "source": url,
    }


def _stale_flag(name, symbol, quote_ts):
    """Return ("keep"|"flag"|"drop", age_days) for a quote's timestamp."""
    if not quote_ts:
        return "keep", None
    age = (datetime.now(UTC) - quote_ts).days
    if age > DROP_AFTER_DAYS:
        print(f"WARN: dropping index {name} ({symbol}); last quote is {age} days old",
              file=sys.stderr)
        return "drop", age
    if age > STALE_AFTER_DAYS:
        print(f"WARN: index {name} ({symbol}) last quoted {age} days ago; flagging stale",
              file=sys.stderr)
        return "flag", age
    return "keep", age


def _fetch_moex_index(name, symbol):
    """MOEX Russia from the exchange's own API.

    Yahoo still answers for IMOEX.ME but its series froze in July 2022, so it
    would publish a four-year-old number as if it were today's close.
    """
    url = ("https://iss.moex.com/iss/engines/stock/markets/index/securities/"
           "IMOEX.json?iss.meta=off")
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    md = resp.json()["marketdata"]
    rec = dict(zip(md["columns"], md["data"][0]))

    price = rec.get("CURRENTVALUE") or rec.get("LASTVALUE")
    if price is None:
        raise ValueError("MOEX returned no index value")

    quote_ts = None
    if rec.get("SYSTIME"):
        quote_ts = datetime.strptime(rec["SYSTIME"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    state, _ = _stale_flag(name, symbol, quote_ts)
    if state == "drop":
        return None

    chg = rec.get("LASTCHANGEPRC")
    row = {
        "name": name,
        "symbol": symbol,
        "value": _fmt(price),
        "chg": f"{chg:+.2f}%" if chg is not None else _pct(rec.get("LASTVALUE"), price),
    }
    if state == "flag":
        row["flag"] = "stale"
    return row


def _fetch_yahoo_index(name, symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    meta = result["meta"]
    closes = [c for c in result["indicators"]["quote"][0]["close"] if c]

    price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
    if price is None:
        raise ValueError("no price in response")

    # Thinly-covered exchanges return only one daily close (or none), which used
    # to make the change silently read +0.00%. The chart's own previous close is
    # the reliable fallback.
    if len(closes) >= 2:
        prev = closes[-2]
    else:
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if not prev:
        raise ValueError("no previous close to compare against")

    quote_ts = None
    if meta.get("regularMarketTime"):
        quote_ts = datetime.fromtimestamp(meta["regularMarketTime"], UTC)
    state, _ = _stale_flag(name, symbol, quote_ts)
    if state == "drop":
        return None

    row = {"name": name, "symbol": symbol, "value": _fmt(price), "chg": _pct(prev, price)}
    if state == "flag":
        row["flag"] = "stale"
    return row


def fetch_indices(entries=None):
    rows = []
    for name, symbol in (INDICES if entries is None else entries):
        try:
            row = (_fetch_moex_index if symbol == "IMOEX" else _fetch_yahoo_index)(name, symbol)
            if row:
                rows.append(row)
        except Exception as exc:
            print(f"WARN: could not fetch index {name} ({symbol}): {exc}", file=sys.stderr)
    return rows


def main():
    now = datetime.now(SYD)
    fx, fx_base, fx_prior = fetch_fx()
    btc = fetch_btc()
    indices = fetch_indices()
    narrative = fetch_indices(NARRATIVE_INDICES)

    out = {
        "as_of": now.strftime("%A %d %B %Y, %H:%M %Z"),
        "btc": btc,
        "btc_crosschecks": [{"source": "CoinGecko API", "price": btc["price"], "chg": btc["chg"]}],
        "fx": fx,
        "fx_base_date": fx_base,
        "fx_prior_date": fx_prior,
        "fx_source": "https://api.frankfurter.dev/v1/latest?from=USD",
        "indices": indices,
        "narrative_indices": narrative,
        "indices_source": "https://finance.yahoo.com/world-indices",
        "indices_asof": now.astimezone(UTC).strftime("%A %d %B %Y, %H:%M %Z"),
        "indices_asof_label": now.strftime("%A %d %B %Y"),
    }

    path = os.path.join(D, "markets.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {path} ({len(fx)} FX rates, {len(indices)} indices, "
          f"{len(narrative)} narrative-only indices)")


if __name__ == "__main__":
    main()
