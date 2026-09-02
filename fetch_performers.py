#!/usr/bin/env python3
"""Fetch fresh regional top gainers/losers for the Market Wrap Up digest.

Writes data/perf-a.json, data/perf-b.json and data/perf-c.json in the schema
build.py already consumes, plus the market_news block that lives in perf-c.

Sources
  ANZ / Japan / Singapore / Hong Kong / China / UK / Germany / Brazil
      TradingView country market-movers pages (HTML scrape).
  US  finance.yahoo.com/gainers and /losers (HTML scrape).
  Mover explainers  Google News RSS, queried per region in the local language.
"""
import json, os, re, sys, time
import html as H
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(D, exist_ok=True)

SYD = ZoneInfo("Australia/Sydney")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
ROWS = 10

# key, title, tv slug, accepted exchange prefixes, link template, price format,
# timezone label, session-source label
MARKETS = [
    {
        "key": "anz", "title": "ANZ Top Performers",
        "slug": "stocks-australia", "prefixes": ["ASX"],
        "link": "https://www.marketindex.com.au/asx/{lower}",
        "price": "${v}", "code_in_name": True, "tz": "AEST",
        "source": "TradingView Australia market movers",
        "extra": ("Covers all ASX-listed stocks rather than the ASX 200 alone. "
                  "Ticker links go to Market Index. New Zealand (NZX) top "
                  "performers are not available from a reliable linked source."),
        "file": "a",
    },
    {
        "key": "japan", "title": "Japan Top Performers",
        "slug": "stocks-japan", "prefixes": ["TSE"],
        "link": "https://www.tradingview.com/symbols/TSE-{code}/",
        "price": "\u00a5{v}", "code_in_name": True, "tz": "JST",
        "source": "TradingView Japan market movers",
        "extra": "Share volumes as reported by TradingView.",
        "file": "a",
    },
    {
        "key": "singapore", "title": "Singapore Top Performers",
        "slug": "stocks-singapore", "prefixes": ["SGX"],
        "link": "https://www.tradingview.com/symbols/SGX-{code}/",
        "price": "S${v}", "code_in_name": True, "tz": "SGT",
        "source": "TradingView Singapore market movers",
        "extra": "Share volumes as reported by TradingView.",
        "file": "a",
    },
    {
        "key": "hongkong", "title": "Hong Kong Top Performers",
        "slug": "stocks-hong-kong", "prefixes": ["HKEX"],
        "link": "https://www.tradingview.com/symbols/HKEX-{code}/",
        "price": "HK${v}", "code_in_name": True, "tz": "HKT",
        "source": "TradingView Hong Kong market movers",
        "extra": "Share volumes as reported by TradingView.",
        "file": "a",
    },
    {
        "key": "china", "title": "China (Mainland) Top Performers",
        "slug": "stocks-china", "prefixes": ["SSE", "SZSE"],
        "link": "https://www.tradingview.com/symbols/{ex}-{code}/",
        "price": "CN\u00a5{v}", "code_in_name": True, "tz": "CST",
        "source": "TradingView Mainland China market movers",
        "extra": ("Mainland boards run daily move limits, so clustering of "
                  "moves at exactly the cap is normal rather than a data error."),
        "file": "b",
    },
    {
        "key": "us", "title": "US Top Performers",
        "slug": None, "prefixes": [],
        "link": "https://finance.yahoo.com/quote/{code}/",
        "price": "${v}", "code_in_name": True, "tz": "ET",
        "source": "Yahoo Finance US market movers",
        "extra": "Share volumes as reported by Yahoo Finance.",
        "file": "b",
    },
    {
        "key": "uk", "title": "UK (London) Top Performers",
        "slug": "stocks-united-kingdom", "prefixes": ["LSE", "AQUIS"],
        "link": "https://www.tradingview.com/symbols/{ex}-{code}/",
        "price": "{v}p", "code_in_name": True, "tz": "BST",
        "source": "TradingView United Kingdom market movers",
        "extra": ("Prices quoted in pence (GBX) as displayed by the exchange. "
                  "Smaller caps may be Aquis-listed rather than LSE main market."),
        "file": "b",
    },
    {
        "key": "germany", "title": "European Top Performers (Germany / XETR)",
        "slug": "stocks-germany", "prefixes": ["XETR"],
        "link": "https://www.tradingview.com/symbols/XETR-{code}/",
        "price": "\u20ac{v}", "code_in_name": False, "tz": "CET",
        "source": "TradingView Germany market movers (Deutsche B\u00f6rse XETR)",
        "extra": "Prices in euros; share volume as published by TradingView.",
        "file": "c",
    },
    {
        "key": "brazil", "title": "Latin American Top Performers (Brazil / B3)",
        "slug": "stocks-brazil", "prefixes": ["BMFBOVESPA"],
        "link": "https://www.tradingview.com/symbols/BMFBOVESPA-{code}/",
        "price": "R${v}", "code_in_name": False, "tz": "BRT",
        "source": "TradingView Brazil market movers (B3)",
        "extra": "Prices in Brazilian reais; share volume as published by TradingView.",
        "file": "c",
    },
]


def get(url):
    resp = requests.get(url, headers=HEADERS, timeout=40)
    resp.raise_for_status()
    return resp.text


def clean(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", "", s))).strip()


# ---------------------------------------------------------------- TradingView

def parse_tradingview(text, prefixes, direction):
    """Return list of {code, ex, name, price, chg, vol} from a movers page."""
    out = []
    for match in re.finditer(r'data-rowkey="([A-Z]+):([A-Za-z0-9.]+)"', text):
        ex, code = match.group(1), match.group(2)
        if ex not in prefixes:
            continue
        chunk = text[match.start():match.start() + 3000]

        name = None
        nm = re.search(r'title="[^"]*\u2212\s*([^"]+)"', chunk)
        if nm:
            name = clean(nm.group(1))
        if not name:
            nm = re.search(r'class="tickerDescription[^"]*"[^>]*>([^<]+)<', chunk)
            if nm:
                name = clean(nm.group(1))
        if not name:
            continue

        # The first coloured span in a row is the Change % column. TradingView
        # renders negatives with a Unicode minus (U+2212), not an ASCII hyphen.
        cm = re.search(
            r'class="(positive|negative)-[A-Za-z0-9_]+"[^>]*>\s*([+\u2212\-]?)\s*([0-9.,]+)%',
            chunk)
        if not cm:
            continue
        pct = float(cm.group(3).replace(",", ""))
        if cm.group(1) == "negative" or cm.group(2) in ("\u2212", "-"):
            pct = -pct

        pm = re.search(r'>([0-9,.]+)<span class="currency-[A-Za-z0-9_]+"', chunk)
        price = pm.group(1) if pm else None
        if not price:
            continue

        vm = re.search(
            r'>([0-9,.]+\s*[KMB]?)</td><td class="cell-[A-Za-z0-9]+ right-[A-Za-z0-9]+">',
            chunk)
        vol = clean(vm.group(1)) if vm else ""
        vol = re.sub(r"\s+([KMB])$", r"\1", vol)

        out.append({"code": code, "ex": ex, "name": name,
                    "price": price, "pct": pct, "vol": vol})
        if len(out) >= ROWS:
            break
    return out


# ---------------------------------------------------------------------- Yahoo

def parse_yahoo(text):
    out = []
    i = text.find("<tbody")
    if i < 0:
        return out
    body = text[i:text.find("</tbody>", i)]
    for row in re.split(r'<tr class="row', body)[1:]:
        tm = re.search(r'href="/quote/([A-Z0-9.\-]+)/?"', row)
        nm = re.search(r'title="([^"]+)" class="leftAlignHeader companyName', row)
        pm = re.search(r'data-testid-cell="intradayprice".*?data-testid="change">([0-9,.]+)', row, re.S)
        cm = re.search(r'data-testid-cell="percentchange".*?data-testid="colorChange">([+\-][0-9.]+)%', row, re.S)
        vm = re.search(r'data-testid-cell="dayvolume".*?data-testid="change">([0-9,.]+[KMB]?)', row, re.S)
        if not (tm and pm and cm):
            continue
        out.append({
            "code": tm.group(1),
            "ex": "",
            "name": clean(nm.group(1)) if nm else tm.group(1),
            "price": pm.group(1),
            "pct": float(cm.group(1)),
            "vol": vm.group(1) if vm else "",
        })
        if len(out) >= ROWS:
            break
    return out


# ----------------------------------------------------------------- formatting

def row_out(cfg, r):
    name = r["name"]
    if cfg["code_in_name"] and not name.endswith(")"):
        name = "%s (%s)" % (name, r["code"])
    url = cfg["link"].format(code=r["code"], lower=r["code"].lower(), ex=r["ex"])
    return {
        "name": name,
        "url": url,
        "price": cfg["price"].format(v=r["price"]),
        "chg": "%+.2f%%" % r["pct"],
        "vol": r["vol"],
    }


# Google News locale per region, so a Frankfurt or B3 mover is researched in the
# language its local press actually reports in. A German small cap is covered by
# German outlets, not English ones, and searching in English finds nothing.
NEWS_LOCALE = {
    "anz":       ("AU", "AU:en",      "ASX shares"),
    "japan":     ("JP", "JP:ja",      "\u682a\u4fa1"),
    "singapore": ("SG", "SG:en",      "SGX shares"),
    "hongkong":  ("HK", "HK:zh-Hant", "\u80a1\u50f9"),
    "china":     ("HK", "HK:zh-Hant", "\u80a1\u4ef7"),
    "us":        ("US", "US:en",      "stock"),
    "uk":        ("GB", "GB:en",      "shares"),
    "germany":   ("DE", "DE:de",      "Aktie"),
    "brazil":    ("BR", "BR:pt-419",  "a\u00e7\u00f5es"),
}

# A catalyst has to sit near the session to explain it. Four days covers a
# Monday move driven by news released over the weekend without reaching back to
# unrelated older coverage.
CATALYST_MAX_AGE_DAYS = 4

# Dropped when matching a headline to a company, since they carry no signal.
_CORP_SUFFIX = {"limited", "ltd", "ltda", "inc", "corp", "corporation", "plc",
                "ag", "sa", "s.a.", "nv", "n.v.", "co", "co.", "company",
                "holdings", "holding", "group", "kgaa", "se", "spa", "ab",
                "asa", "oyj", "bhd", "pte", "pty", "the", "and"}

# Quote, chart and screener pages rank well for a company name but report
# nothing. Citing one as the reason a stock moved would be misleading, so they
# are rejected outright rather than used as a weak catalyst.
_NOISE_TITLE = re.compile(
    r"(\u682a\u4fa1\u30c1\u30e3\u30fc\u30c8|\u63b2\u793a\u677f|\u6d41\u52a8\u6bd4\u7387"
    r"|\u884c\u60c5|\u5be6\u6642\u5831\u50f9"
    r"|stock price and chart|price and chart|chart-analyse|technische analyse"
    r"|aktienkurs|kursziel|chart\s*\||\bquote\b|cota\u00e7\u00f5es"
    r"|share price history|dividend history)", re.I)

_NOISE_PUBLISHER = {"tradingview", "moomoo", "wallmine", "investing.com",
                    "marketscreener", "simply wall st", "stockinvest.us",
                    "yahoo!\u30d5\u30a1\u30a4\u30ca\u30f3\u30b9"}


def _news_items(query, gl, ceid):
    """Recent press for a query, newest first. Returns [] rather than raising."""
    url = ("https://news.google.com/rss/search?q=%s&hl=en-%s&gl=%s&ceid=%s"
           % (urllib.parse.quote(query), gl, gl, ceid))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate"))
        except Exception:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        source = item.find("source")
        out.append({
            "title": title,
            "url": link,
            "publisher": (source.text or "").strip() if source is not None else "",
            "published": published,
        })
    out.sort(key=lambda x: x["published"], reverse=True)
    return out


def _name_tokens(name):
    """Distinctive words in a company name, for matching against a headline."""
    cleaned = re.sub(r"[^\w\s]", " ", name, flags=re.UNICODE)
    tokens = [t for t in cleaned.lower().split()
              if len(t) >= 4 and t not in _CORP_SUFFIX]
    # CJK names do not split on spaces, so fall back to the leading characters.
    if not tokens and len(name.strip()) >= 2:
        tokens = [name.strip()[:4].lower()]
    return tokens


def catalyst(cfg, r, now):
    """Find a genuine, recent, on-topic article explaining a mover.

    Returns None when nothing qualifies. That is a real answer: thin micro-caps
    frequently move with no reported reason, and inventing one would be worse
    than saying so.
    """
    if r is None:
        return None
    gl, ceid, hint = NEWS_LOCALE.get(cfg["key"], ("US", "US:en", "stock"))
    base = re.sub(r"\s*\([^)]*\)\s*$", "", r["name"]).strip()
    tokens = _name_tokens(base)
    if not tokens:
        return None
    cutoff = now - timedelta(days=CATALYST_MAX_AGE_DAYS)
    for query in ('"%s" %s' % (base, hint), "%s %s" % (base, hint)):
        for item in _news_items(query, gl, ceid):
            if item["published"] < cutoff:
                break          # sorted newest first, so the rest are older too
            if _NOISE_TITLE.search(item["title"]):
                continue
            if item["publisher"].strip().lower() in _NOISE_PUBLISHER:
                continue
            if any(t in item["title"].lower() for t in tokens):
                return item
        time.sleep(0.5)
    return None


def note(cfg, r, kind, hit):
    """Explainer for a region's biggest mover, rebuilt from this run's data."""
    if r is None:
        return ("No %s could be retrieved from %s for this session, so no "
                "explainer is offered rather than publishing an unverified one."
                % (kind, cfg["source"]))
    verb = "led" if kind == "gainer" else "was the steepest decliner on"
    direction = "up" if kind == "gainer" else "down"
    vol = (" on reported volume of %s shares" % r["vol"]) if r["vol"] else ""
    opening = (
        "%s %s the %s board for the session, %s %.2f per cent to %s%s."
        % (r["name"], verb, cfg["title"].split(" Top")[0], direction,
           abs(r["pct"]), cfg["price"].format(v=r["price"]), vol))
    if hit:
        return ("%s Reported alongside the move, %s on %s:"
                % (opening, hit["publisher"] or "the local press",
                   hit["published"].astimezone(SYD).strftime("%d %B %Y")))
    return ("%s The move is reported here as captured from %s at the time of "
            "this build. No company announcement covering it could be found in "
            "the local press, so no catalyst is asserted - a common outcome for "
            "a thinly traded stock." % (opening, cfg["source"]))


def _source_out(hit):
    """Serialise a catalyst hit for the builder, or [] when there was none."""
    if not hit:
        return []
    return [{
        "title": hit["title"],
        "url": hit["url"],
        "publisher": hit["publisher"],
        "published": hit["published"].astimezone(SYD).isoformat(timespec="seconds"),
    }]


def caption(cfg, stamp):
    # The stamp is this build's Sydney clock time, so it is labelled AEST rather
    # than the exchange's own timezone; the session it captures is whatever that
    # exchange was last showing at that moment.
    return ("Source: %s, captured %s AEST, covering the %s session most recently "
            "published at that time. %s" % (cfg["source"], stamp, cfg["tz"], cfg["extra"]))


# ----------------------------------------------------------------- market news

def market_news(now):
    """Build the Market News paragraph from the freshly fetched index data."""
    try:
        mk = json.load(open(os.path.join(D, "markets.json")))
    except Exception:
        return None

    # The paragraph also names benchmarks that are no longer in the 24-cell grid
    # (Dow, Russell 2000, All Ordinaries, Straits Times), which are fetched
    # alongside it purely so this summary keeps its regional coverage.
    idx = {i["name"]: i for i in
           mk.get("indices", []) + mk.get("narrative_indices", [])}

    def phr(name, label=None):
        i = idx.get(name)
        if not i:
            return None
        pct = float(i["chg"].rstrip("%"))
        if abs(pct) < 0.05:
            move = "was little changed at"
        elif pct > 0:
            move = "rose %.2f per cent to" % pct
        else:
            move = "fell %.2f per cent to" % abs(pct)
        return "the %s %s %s" % (label or name, move, i["value"])

    def group(names):
        return [p for p in (phr(n) for n in names) if p]

    us = group(["S&P 500", "Dow Jones", "Nasdaq Composite", "Russell 2000"])
    eu = group(["FTSE 100", "DAX", "CAC 40"])
    asia = group(["Nikkei 225", "Hang Seng", "KOSPI", "Shanghai Composite",
                  "BSE Sensex", "Straits Times"])
    other = group(["Ibovespa"])
    au = group(["S&P/ASX 200", "All Ordinaries"])

    if not us and not asia and not au:
        return None

    ups = sum(1 for i in mk.get("indices", []) if float(i["chg"].rstrip("%")) > 0)
    total = len(mk.get("indices", []))
    tone = ("broadly firmer" if ups > total * 0.6 else
            "broadly weaker" if ups < total * 0.4 else "mixed")

    btc = mk.get("btc", {})
    fx = {f["code"]: f for f in mk.get("fx", [])}

    parts = []
    parts.append("Global equities were %s in the latest completed round of "
                 "trading, with %d of the %d benchmarks tracked on this page "
                 "closing higher." % (tone, ups, total))
    if us:
        parts.append("In the United States, %s." % _join(us))
    if eu:
        parts.append("In Europe, %s." % _join(eu))
    if asia:
        parts.append("Across Asia, %s." % _join(asia))
    if other:
        parts.append("Elsewhere, %s." % _join(other))
    if au:
        parts.append("Locally, %s." % _join(au))

    if btc.get("price"):
        parts.append("In digital assets, bitcoin changed hands at %s, %s over "
                     "the past 24 hours." % (btc["price"], _chg_words(btc.get("chg", ""))))

    aud = fx.get("AUD")
    if aud:
        parts.append("In currencies, the US dollar bought %s Australian dollars, "
                     "%s against the prior business day's fix." %
                     (aud["rate"], _chg_words(aud["chg"])))

    parts.append("Index levels, exchange rates and commodity prices on this page "
                 "are captured live at build time from the sources linked in each "
                 "section; no forward-looking view is offered here.")

    paragraph = " ".join(parts)

    caption_txt = ("Market data on this page was captured at %s, reflecting the "
                   "most recent completed or in-progress session at each of the "
                   "exchanges listed." % now.strftime("%A %d %B %Y at %H:%M %Z"))

    return {
        "paragraph": paragraph,
        "fetched": now.isoformat(timespec="seconds"),
        "stale": False,
        "sources": [
            {"title": "Yahoo Finance world indices", "url": "https://finance.yahoo.com/world-indices"},
            {"title": "Frankfurter foreign exchange reference rates", "url": "https://api.frankfurter.dev/v1/latest?from=USD"},
            {"title": "CoinGecko bitcoin price", "url": "https://www.coingecko.com/en/coins/bitcoin"},
        ],
        "asof_caption": caption_txt,
    }


def _join(items):
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _chg_words(chg):
    if not chg:
        return "little changed"
    try:
        v = float(chg.rstrip("%"))
    except ValueError:
        return "little changed"
    if abs(v) < 0.005:
        return "little changed"
    return ("up %.2f per cent" if v > 0 else "down %.2f per cent") % abs(v)


# ------------------------------------------------------------------------ run

def fetch_market(cfg):
    if cfg["slug"] is None:
        gainers = parse_yahoo(get("https://finance.yahoo.com/gainers"))
        losers = parse_yahoo(get("https://finance.yahoo.com/losers"))
    else:
        base = "https://www.tradingview.com/markets/%s/market-movers-%s/"
        gainers = parse_tradingview(get(base % (cfg["slug"], "gainers")),
                                    cfg["prefixes"], "gainers")
        losers = parse_tradingview(get(base % (cfg["slug"], "losers")),
                                   cfg["prefixes"], "losers")
    return gainers, losers


# A region must yield at least this many rows on each side to be publishable.
# Below this the scrape is treated as broken rather than as a thin market.
MIN_ROWS = 5
ATTEMPTS = 3


def fetch_market_with_retry(cfg):
    """Pull a region, retrying transient scrape failures before giving up.

    Every run must genuinely re-pull each region, so a partial result is
    retried rather than quietly accepted.
    """
    last_error = None
    best = ([], [])
    for attempt in range(1, ATTEMPTS + 1):
        try:
            gainers, losers = fetch_market(cfg)
        except Exception as exc:
            last_error = exc
            gainers, losers = [], []
        if len(gainers) >= ROWS and len(losers) >= ROWS:
            return gainers, losers, None
        if min(len(gainers), len(losers)) > min(len(best[0]), len(best[1])):
            best = (gainers, losers)
        if attempt < ATTEMPTS:
            print("    %s attempt %d/%d thin (g=%d l=%d), retrying"
                  % (cfg["key"], attempt, ATTEMPTS, len(gainers), len(losers)),
                  file=sys.stderr)
            time.sleep(3 * attempt)

    gainers, losers = best
    if len(gainers) >= MIN_ROWS and len(losers) >= MIN_ROWS:
        return gainers, losers, None
    reason = ("fetch error: %s" % last_error if last_error
              else "only g=%d l=%d rows after %d attempts"
                   % (len(gainers), len(losers), ATTEMPTS))
    return None, None, reason


def main():
    now = datetime.now(SYD)
    stamp = now.strftime("%A %d %B %Y at %H:%M")
    iso = now.isoformat(timespec="seconds")
    buckets = {"a": [], "b": [], "c": []}
    failures = []

    for cfg in MARKETS:
        gainers, losers, reason = fetch_market_with_retry(cfg)
        if reason:
            print("WARN: %s could not be refreshed this run (%s)"
                  % (cfg["key"], reason), file=sys.stderr)
            failures.append((cfg["key"], reason))
            continue

        g_hit = catalyst(cfg, gainers[0] if gainers else None, now)
        l_hit = catalyst(cfg, losers[0] if losers else None, now)

        buckets[cfg["file"]].append({
            "key": cfg["key"],
            "title": cfg["title"],
            "caption": caption(cfg, stamp),
            "fetched": iso,
            "stale": False,
            "gainer_note": note(cfg, gainers[0] if gainers else None, "gainer", g_hit),
            "gainer_note_sources": _source_out(g_hit),
            "loser_note": note(cfg, losers[0] if losers else None, "loser", l_hit),
            "loser_note_sources": _source_out(l_hit),
            "gainers": [row_out(cfg, r) for r in gainers],
            "losers": [row_out(cfg, r) for r in losers],
        })
        print("  %-10s gainers=%d losers=%d catalyst: gainer=%s loser=%s"
              % (cfg["key"], len(gainers), len(losers),
                 "yes" if g_hit else "none", "yes" if l_hit else "none"))
        time.sleep(1)

    order = {"a": ["anz", "japan", "singapore", "hongkong"],
             "b": ["china", "us", "uk"],
             "c": ["germany", "brazil"]}

    for letter, keys in order.items():
        path = os.path.join(D, "perf-%s.json" % letter)
        existing = {}
        try:
            prev = json.load(open(path))
            existing = {m["key"]: m for m in prev.get("markets", [])}
        except Exception:
            prev = {}
        fresh = {m["key"]: m for m in buckets[letter]}

        merged = []
        for k in keys:
            if k in fresh:
                merged.append(fresh[k])
                continue
            old = existing.get(k)
            if not old:
                continue
            # Carry the previous rows through so the page still renders, but
            # mark them so build.py can refuse to publish a stale region rather
            # than passing off an old session's movers as today's.
            old = dict(old)
            old["stale"] = True
            old.setdefault("fetched", "1970-01-01T00:00:00+00:00")
            merged.append(old)

        out = {"markets": merged}
        if letter == "c":
            mn = market_news(now)
            if mn is None:
                # The opening Market News paragraph is derived from markets.json.
                # If that could not be read, carry the previous text but mark it
                # so build.py refuses to publish last run's market recap as this
                # run's.
                print("WARN: could not build market news from markets.json; "
                      "previous paragraph retained and flagged stale",
                      file=sys.stderr)
                mn = dict(prev.get("market_news") or {})
                mn["stale"] = True
                mn.setdefault("fetched", "1970-01-01T00:00:00+00:00")
                failures.append(("market_news", "markets.json unreadable or empty"))
            out = {"market_news": mn, "markets": merged}

        with open(path, "w") as f:
            json.dump(out, f, indent=1)
        print("wrote %s (%d markets)" % (path, len(merged)))

    if failures:
        for key, reason in failures:
            print("STALE: %s is carrying the previous run's movers (%s)"
                  % (key, reason), file=sys.stderr)
        print("%d of %d regions could not be refreshed; build.py will refuse to "
              "publish them." % (len(failures), len(MARKETS)), file=sys.stderr)
        return 1
    print("all %d regions refreshed" % len(MARKETS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
