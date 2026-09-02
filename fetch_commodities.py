#!/usr/bin/env python3
"""Fetch fresh commodity prices for the Market Wrap Up digest.
Falls back to tradingeconomics.com meta descriptions for most items and
Kitco for precious-metals cross-checks. Rare earths uses MP Materials as a proxy.
"""
import json, os, re, sys, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from newsfeed import is_noise, news_items

import requests

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(D, exist_ok=True)
SYD = ZoneInfo("Australia/Sydney")

# 24 commodities, grouped by family so the 4-column grid reads a row at a time:
# energy, precious metals, base metals, bulk/battery/nuclear, then agriculture.
COMMODITIES = [
    ("Petroleum (WTI)", "crude-oil", "USD/Bbl", None),
    ("Brent Crude", "brent-crude-oil", "USD/Bbl", None),
    ("Natural Gas", "natural-gas", "USD/MMBtu", None),
    ("Coal (Newcastle)", "coal", "USD/T", None),
    ("Gold", "gold", "USD/t oz", "https://www.kitco.com/charts/gold"),
    ("Silver", "silver", "USD/t oz", "https://www.kitco.com/charts/silver"),
    ("Platinum", "platinum", "USD/t oz", "https://www.kitco.com/charts/platinum"),
    ("Palladium", "palladium", "USD/t oz", "https://www.kitco.com/charts/palladium"),
    ("Rhodium", "rhodium", "USD/t oz", "https://www.kitco.com/charts/rhodium"),
    ("Copper", "copper", "USD/Lbs", None),
    ("Aluminum", "aluminum", "USD/T", None),
    ("Nickel", "nickel", "USD/T", None),
    ("Zinc", "zinc", "USD/T", None),
    ("Lead", "lead", "USD/T", None),
    ("Tin", "tin", "USD/T", None),
    ("Iron Ore 62% Fe", "iron-ore", "USD/T", None),
    ("Lithium (carbonate)", "lithium", "CNY/T", None),
    ("Cobalt", "cobalt", "USD/T", None),
    ("Rare Earth Elements", "rare-earths", "USD/share", None),  # proxy below
    ("Uranium (U3O8)", "uranium", "USD/Lbs", None),
    ("Wheat", "wheat", "USd/Bu", None),
    ("Corn", "corn", "USd/Bu", None),
    ("Soybeans", "soybeans", "USd/Bu", None),
    ("Sugar", "sugar", "USd/Lbs", None),
]


def _parse_tradingeconomics(slug):
    url = f"https://tradingeconomics.com/commodity/{slug}"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        resp.raise_for_status()
        text = resp.text
        m = re.search(r'name="description" content="([^"]+)"', text)
        if not m:
            return None
        desc = m.group(1)
        # "Crude Oil fell to 83.44 USD/Bbl on August 28, 2026, down 0.11% from the previous day."
        # "Coal rose to 139.75 USD/T on August 28, 2026, up 0.18% from the previous day."
        # "Cobalt traded flat at 56,290 USD/T on August 27, 2026."
        pm = re.search(
            r"([A-Za-z\s]+?)\s+(fell|rose|traded flat)\s+(?:to|at)\s+([0-9,.]+)\s+([A-Za-z/\.\s]+?)\s+on\s+(.+?),\s*(?:(down|up)\s+([0-9.]+)%|traded flat)",
            desc,
        )
        if not pm:
            # Handle "traded flat at ..." variant without a percentage clause.
            pm = re.search(
                r"([A-Za-z\s]+?)\s+(traded flat)\s+at\s+([0-9,.]+)\s+([A-Za-z/\.\s]+?)\s+on\s+(.+?)",
                desc,
            )
            if pm:
                name, direction, price, _unit, date_txt = pm.groups()
                return {"price": price.replace(",", ""), "chg": "0.00%",
                        "asof": _parse_desc_date(date_txt)}
            return None
        name, direction, price, _unit, date_txt, chg_dir, chg_val = pm.groups()
        if direction == "traded flat":
            chg = "0.00%"
        else:
            sign = "+" if chg_dir == "up" else "-"
            chg = f"{sign}{chg_val}%"
        return {"price": price.replace(",", ""), "chg": chg,
                "asof": _parse_desc_date(date_txt)}
    except Exception as exc:
        print(f"WARN: tradingeconomics fetch failed for {slug}: {exc}", file=sys.stderr)
        return None


def _parse_kitco(metal):
    url = f"https://www.kitco.com/charts/{metal}"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        resp.raise_for_status()
        text = resp.text
        price_m = re.search(r'ounce</p><p[^>]*>([0-9,.]+)</p>', text)
        pct_m = re.search(r'\(\s*<!--\s*-->(-?\d+\.\d+)%\s*<!--\s*-->\)', text)
        if price_m and pct_m:
            return {"price": price_m.group(1).replace(",", ""), "chg": pct_m.group(1) + "%"}
    except Exception as exc:
        print(f"WARN: Kitco fetch failed for {metal}: {exc}", file=sys.stderr)
    return None


def _mp_materials_proxy():
    """Use MP Materials (NYSE: MP) as a proxy for rare earth elements."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/MP?interval=1d&range=5d"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
        meta = result["meta"]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
        price = meta.get("regularMarketPrice") or closes[-1]
        prev = closes[-2] if len(closes) >= 2 else closes[-1]
        chg = (price - prev) / prev * 100 if prev else 0.0
        return {
            "price": f"{price:.2f}",
            "chg": f"{chg:+.2f}%",
            "flag": "proxy",
            "url": "https://finance.yahoo.com/quote/MP",
        }
    except Exception as exc:
        print(f"WARN: MP Materials proxy failed: {exc}", file=sys.stderr)
    return None


# A quote more than one day behind the run is disclosed to the reader. Several
# of these contracts (cobalt, uranium, Newcastle coal) are fixed weekly or
# monthly rather than traded continuously, so a flat print is normal - but the
# page should say so instead of implying it is a live daily move.
STALE_AFTER_DAYS = 1


def _parse_desc_date(date_txt):
    """The quote date from a tradingeconomics description, as ISO or None."""
    if not date_txt:
        return None
    m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})", date_txt)
    if not m:
        return None
    try:
        return datetime.strptime(" ".join(m.groups()), "%B %d %Y").date().isoformat()
    except ValueError:
        return None


def _stale_flag(asof, today):
    """Flag a commodity whose source quote has not refreshed past the prior day."""
    if not asof:
        return None
    try:
        quoted = datetime.strptime(asof, "%Y-%m-%d").date()
    except ValueError:
        return None
    return "stale" if (today - quoted).days > STALE_AFTER_DAYS else None


# The grid's families, used to describe the complex a row at a time rather than
# listing 24 prices back at the reader.
FAMILIES = [
    ("energy", "was",
     ["Petroleum (WTI)", "Brent Crude", "Natural Gas", "Coal (Newcastle)"]),
    ("precious metals", "were",
     ["Gold", "Silver", "Platinum", "Palladium", "Rhodium"]),
    ("base metals", "were",
     ["Copper", "Aluminum", "Nickel", "Zinc", "Lead", "Tin"]),
    ("bulk and battery materials", "were",
     ["Iron Ore 62% Fe", "Lithium (carbonate)", "Cobalt", "Uranium (U3O8)",
      "Rare Earth Elements"]),
    ("agriculture", "was", ["Wheat", "Corn", "Soybeans", "Sugar"]),
]


def _pct(row):
    try:
        return float(row["chg"].replace("%", "").replace("+", ""))
    except (ValueError, KeyError):
        return 0.0


def _family_clause(label, rows, verb="was"):
    """One clause describing how a family traded, named after its biggest move."""
    if not rows:
        return None
    up = [r for r in rows if _pct(r) > 0]
    down = [r for r in rows if _pct(r) < 0]
    lead = max(rows, key=lambda r: abs(_pct(r)))
    if not up and not down:
        return "%s %s unchanged across all %d benchmarks" % (label, verb, len(rows))
    uniform = len(up) == len(rows) or len(down) == len(rows)
    if len(up) == len(rows):
        shape = "%s advanced across the board" % label
    elif len(down) == len(rows):
        shape = "%s fell across the board" % label
    else:
        shape = "%s %s mixed, %d of %d higher" % (label, verb, len(up), len(rows))
    if abs(_pct(lead)) < 0.005:
        return shape
    # "led by" only reads correctly when the family moved as one. In a mixed
    # family the biggest move often runs against the majority, so name it
    # neutrally instead of implying it led an advance.
    joiner = "led by" if uniform else "the biggest move coming from"
    return ("%s, %s %s at %s to %s %s"
            % (shape, joiner, lead["name"], lead["chg"], lead["price"], lead["unit"]))


# A market wrap reports movement; a vendor press release ("X expands its
# commodity offering") matches the same keywords but explains nothing.
_MOVE_WORDS = re.compile(
    r"\b(rise|rises|rose|rising|fall|falls|fell|falling|climb|climbs|slip|slips"
    r"|gain|gains|drop|drops|jump|jumps|plunge|plunges|surge|surges|steady"
    r"|higher|lower|rally|rallies|retreat|retreats|edge|edges|slide|slides"
    r"|weaken|weakens|firmer|softer|outlook|forecast)\b", re.I)


def _market_article(now):
    """A real, recent commodities market report to ground the summary."""
    cutoff = now - timedelta(days=2)
    best = None
    for query in ("gold oil copper prices today market wrap",
                  "commodity prices gold crude oil close",
                  "commodities market outlook gold oil copper"):
        for item in news_items(query, "US", "US:en"):
            if item["published"] < cutoff or is_noise(item):
                continue
            if _MOVE_WORDS.search(item["title"]):
                return item
            best = best or item      # keep as a fallback if nothing better lands
        time.sleep(0.5)
    return best


def build_summary(rows, now, article=None):
    """Rebuild the commodities paragraph from this run's own prices.

    Written fresh every run. When no prices survived the fetch the paragraph
    says so rather than describing a complex it could not measure.
    """
    if not rows:
        return ("No commodity prices could be retrieved for this session, so "
                "no summary of the complex is offered rather than publishing "
                "an unverified one.")
    by_name = {r["name"]: r for r in rows}
    clauses = [c for c in
               (_family_clause(label, [by_name[n] for n in names if n in by_name],
                               verb)
                for label, verb, names in FAMILIES) if c]
    advancers = sum(1 for r in rows if _pct(r) > 0)
    decliners = sum(1 for r in rows if _pct(r) < 0)
    if advancers > decliners:
        tone = "broadly firmer"
    elif decliners > advancers:
        tone = "broadly weaker"
    else:
        tone = "evenly split"
    body = "; ".join(clauses)
    text = ("Commodities were %s in the latest session, with %d of the %d "
            "tracked benchmarks higher and %d lower. %s."
            % (tone, advancers, len(rows), decliners,
               body[:1].upper() + body[1:] if body else ""))
    biggest = max(rows, key=lambda r: abs(_pct(r)))
    if abs(_pct(biggest)) >= 0.005:
        text += (" The largest single move across the complex was %s at %s."
                 % (biggest["name"], biggest["chg"]))
    stale = [r["name"] for r in rows if r.get("flag") == "stale"]
    if stale:
        text += (" %s %s not refreshed past the prior day's print and %s "
                 "flagged accordingly, being fixed periodically rather than "
                 "traded continuously."
                 % (", ".join(stale), "has" if len(stale) == 1 else "have",
                    "is" if len(stale) == 1 else "are"))
    text += (" Rare earths are represented by the MP Materials equity proxy, as "
             "no reliable daily spot benchmark is published.")
    if article:
        text += (" Reported alongside the session, %s on %s:"
                 % (article["publisher"] or "the trade press",
                    article["published"].astimezone(SYD).strftime("%d %B %Y")))
    return text


def main():
    now = datetime.now(SYD)
    today = now.date()
    rows = []
    for name, slug, unit, kitco_url in COMMODITIES:
        if slug == "rare-earths":
            proxy = _mp_materials_proxy()
            if proxy is None:
                # Previously fell back to a hardcoded 62.20 at +0.00%, which put
                # an invented price on the page. Drop the cell instead, exactly
                # as every other commodity does when its fetch fails.
                print(f"WARN: could not fetch {name} proxy; dropping the cell",
                      file=sys.stderr)
                continue
            rows.append({
                "name": name,
                "price": proxy["price"],
                "unit": unit,
                "chg": proxy["chg"],
                "url": proxy["url"],
                "flag": "proxy",
                "source": "yahoo-finance-proxy",
            })
            continue

        data, source = None, "tradingeconomics"
        if kitco_url:
            data = _parse_kitco(slug)
            if data is not None:
                source = "kitco"

        if data is None:
            data = _parse_tradingeconomics(slug)

        if data is None:
            # Publishing a 0.00 placeholder would put an invented price on the
            # page, so the cell is dropped instead and the grid runs one short.
            print(f"WARN: could not fetch {name}; dropping the cell", file=sys.stderr)
            continue

        rows.append({
            "name": name,
            "price": data["price"],
            "unit": unit,
            "chg": data["chg"],
            "url": f"https://tradingeconomics.com/commodity/{slug}",
            "flag": _stale_flag(data.get("asof"), today),
            "source": source,
            "asof": data.get("asof"),
        })

    article = _market_article(now)
    out = {
        "as_of": now.isoformat(),
        "summary": build_summary(rows, now, article),
        "summary_sources": ([{"title": article["title"], "url": article["url"],
                              "publisher": article["publisher"]}]
                            if article else []),
        "commodities": rows,
    }

    path = os.path.join(D, "commodities.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    stale_n = sum(1 for r in rows if r.get("flag") == "stale")
    print(f"wrote {path} ({len(rows)} commodities, {stale_n} stale, "
          f"catalyst={'yes' if article else 'none'})")


if __name__ == "__main__":
    main()
