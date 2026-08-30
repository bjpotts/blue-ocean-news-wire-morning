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

INDICES = [
    ("S&P 500", "^GSPC"),
    ("Dow Jones", "^DJI"),
    ("Nasdaq Composite", "^IXIC"),
    ("Russell 2000", "^RUT"),
    ("S&P/ASX 200", "^AXJO"),
    ("All Ordinaries", "^AORD"),
    ("FTSE 100", "^FTSE"),
    ("DAX", "^GDAXI"),
    ("CAC 40", "^FCHI"),
    ("Hang Seng", "^HSI"),
    ("Nikkei 225", "^N225"),
    ("KOSPI", "^KS11"),
    ("SSE Composite", "000001.SS"),
    ("Ibovespa", "^BVSP"),
    ("Straits Times", "^STI"),
    ("BSE Sensex", "^BSESN"),
]


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


def fetch_indices():
    rows = []
    for name, symbol in INDICES:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            resp.raise_for_status()
            result = resp.json()["chart"]["result"][0]
            meta = result["meta"]
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
            price = meta.get("regularMarketPrice") or closes[-1]
            prev = closes[-2] if len(closes) >= 2 else closes[-1]
            rows.append({
                "name": name,
                "symbol": symbol,
                "value": _fmt(price),
                "chg": _pct(prev, price),
            })
        except Exception as exc:
            print(f"WARN: could not fetch index {name} ({symbol}): {exc}", file=sys.stderr)
    return rows


def main():
    now = datetime.now(SYD)
    fx, fx_base, fx_prior = fetch_fx()
    btc = fetch_btc()
    indices = fetch_indices()

    out = {
        "as_of": now.strftime("%A %d %B %Y, %H:%M %Z"),
        "btc": btc,
        "btc_crosschecks": [{"source": "CoinGecko API", "price": btc["price"], "chg": btc["chg"]}],
        "fx": fx,
        "fx_base_date": fx_base,
        "fx_prior_date": fx_prior,
        "fx_source": "https://api.frankfurter.dev/v1/latest?from=USD",
        "indices": indices,
        "indices_source": "https://finance.yahoo.com/world-indices",
        "indices_asof": now.astimezone(UTC).strftime("%A %d %B %Y, %H:%M %Z"),
        "indices_asof_label": now.strftime("%A %d %B %Y"),
    }

    path = os.path.join(D, "markets.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {path} ({len(fx)} FX rates, {len(indices)} indices)")


if __name__ == "__main__":
    main()
