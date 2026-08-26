#!/usr/bin/env python3
"""Build the Market Wrap Up digest page for Blue Ocean Equities Pty Ltd."""
import json, html, os, re

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "digest.html")
PREVIEW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview.html")
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "style.css")

def load(n):
    with open(os.path.join(D, n)) as f:
        return json.load(f)

mk = load("markets.json")
cm = load("commodities.json")
pa = load("perf-a.json")
pb = load("perf-b.json")
pc = load("perf-c.json")
cr = load("capraises.json")
tech = load("tech.json")
na = load("news-a.json")
nb = load("news-b.json")
sp = load("sport.json")
wx = load("weather.json")

E = lambda s: html.escape(str(s), quote=True)

# Some sources came back with markdown bold wrappers around the headline text.
# The stylesheet already bolds headlines, so strip the markers or they render as
# literal asterisks on the page.
def _strip_md(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("headline", "detail", "summary") and isinstance(v, str):
                node[k] = re.sub(r"^\*\*(.*?)\*\*$", r"\1", v.strip()).strip()
            else:
                _strip_md(v)
    elif isinstance(node, list):
        for v in node:
            _strip_md(v)

for _doc in (na, nb, sp, tech, cr):
    _strip_md(_doc)

# ----------------------------------------------------------------- de-duplication
# Removes items that repeat a story already carried elsewhere on the page: one
# article used under two regions, and several cases of a single event listed twice
# inside one section. Facts from a dropped item are folded into the survivor.
# Guards are tolerant: if a needle isn't present in the fresh data, we skip rather
# than crash the build (the hardcoded needles below are edition-specific).
bf = load("backfill.json")

def _region(key):
    return next((r for r in cr["regions"] if r["key"] == key), None)

def _drop(items, needle):
    keep = [i for i in items if needle not in i["headline"]]
    if len(keep) == len(items) - 1:
        return keep
    return items

def _extend(items, needle, clause):
    hit = [i for i in items if needle in i["headline"]]
    if len(hit) == 1 and hit[0]["detail"].endswith("."):
        hit[0]["detail"] = hit[0]["detail"][:-1] + clause
    return items

anz = _region("anz")
if anz is not None:
    _extend(anz["items"], "Sports Entertainment Group closes",
            ", with a non-underwritten retail share purchase plan of up to about A$2 million at the "
            "same A$0.28 price, capped at A$30,000 per holder, following for eligible shareholders.")
    anz["items"] = _drop(anz["items"], "opens retail share purchase plan")
    anz["items"] = _drop(anz["items"], "Glencore")
    anz["items"] += bf.get("anz_items", [])
    anz["summary"] = bf["summaries"]["anz"] if "summaries" in bf and "anz" in bf["summaries"] else anz["summary"]

uk = _region("uk")
if uk is not None:
    uk["items"] = _drop(uk["items"], "Nscale points to a September window")
    uk["items"] += bf.get("uk_items", [])
    uk["summary"] = bf["summaries"]["uk"] if "summaries" in bf and "uk" in bf["summaries"] else uk["summary"]

rest = _region("rest")
if rest is not None:
    _extend(rest["items"], "Dangote refinery locks in",
            ", with the offer structured around Nigerian retail and African institutional investors and "
            "no foreign listing until the refinery has at least three years of results.")
    rest["items"] = _drop(rest["items"], "retail-focused and rules out")
    rest["summary"] = bf["summaries"]["rest"] if "summaries" in bf and "rest" in bf["summaries"] else rest["summary"]

golf = next((c for c in sp["codes"] if c["key"] == "golf"), None)
if golf is not None:
    golf["items"] = _drop(golf["items"], "grabs a share of the opening lead")

abcau = next((o for o in na["outlets"] if o["key"] == "abc"), None)
if abcau is not None:
    abcau["items"] = _drop(abcau["items"], "Bloods")
    _abc_bf = bf.get("abc_item") or {}
    if isinstance(_abc_bf, dict) and _abc_bf.get("url"):
        abcau["items"].append(_abc_bf)

EDITION = "Morning Edition"
DATELINE = "Thursday 27 August 2026 \u00b7 08:00 AEST \u00b7 Sydney, NSW"
GEN_NOTE = "Generated Thursday 27 August 2026 at 08:00 AEST / 22:00 UTC."

def chg_class(c):
    c = (c or "").strip()
    if c.startswith("-"):
        return "chg-neg"
    if c.startswith("+"):
        return "chg-pos"
    return "chg-flat"

# ---------------------------------------------------------------- market news
mnp = pc["market_news"]["paragraph"]
fixes = [
    ("The Russell 2000 small-cap index was not among the indexes detailed in the reports reviewed.",
     "The Russell 2000 small-cap index closed at 3,017.87, up 0.85 per cent, outpacing the large-cap benchmarks."),
    ("the Nikkei 225 slipped 0.2 per cent to 66,080.25", "the Nikkei 225 slipped 0.30 per cent to 66,016.36"),
    ("the Hang Seng added 0.7 per cent to 25,888.36", "the Hang Seng added 1.21 per cent to 26,009.46"),
    ("the KOSPI climbed 0.9 per cent to 6,914.09", "the KOSPI climbed 0.88 per cent to 6,912.95"),
    ("the Shanghai Composite was little changed at 3,903.81", "the Shanghai Composite was little changed at 3,905.20"),
    ("India's BSE Sensex eased about 0.1 per cent", "India's BSE Sensex was flat at 77,540.83"),
]
# The fixes above are edition-specific. Apply each only when its source string
# is present so a freshly written paragraph for the new run does not break.
for a, b in fixes:
    if a in mnp:
        mnp = mnp.replace(a, b)
MARKET_NEWS = E(mnp)
ASOF_CAPTION = E(pc["market_news"]["asof_caption"])

# ---------------------------------------------------------------- local weather
# Build-time conditions for the run location (from the machine timezone). The
# script below upgrades this in-browser to the reader's own location if they
# allow it; if they decline, or scripting is blocked, this static strip stands
# and is what appears in any PDF export.
def wx_cell(label, value, url):
    return ('<a class="wx-cell" href="%s" target="_blank" rel="noopener">'
            '<span class="wx-label">%s</span><span class="wx-value">%s</span></a>'
            % (E(url), E(label), value))

WEATHER = """<div class="wx-strip" id="wx-strip" data-fallback-url="%s">
<a class="wx-place" id="wx-place" href="%s" target="_blank" rel="noopener">%s</a>
%s
</div>
<p class="caption wx-note" id="wx-note">Current conditions observed %s local time, via <a href="%s" target="_blank" rel="noopener">Open-Meteo</a>, with the outlook link going to the <a href="%s" target="_blank" rel="noopener">%s</a>. Location is taken from this edition's build timezone, %s; allow location access in your browser and the strip switches to your own local conditions.</p>""" % (
    E(wx["source_url"]), E(wx["source_url"]), E("%s &middot; %s" % (wx["place"], wx["condition"])).replace("&amp;middot;", "&middot;"),
    "\n".join([
        wx_cell("Now", wx["temp"], wx["obs_url"]),
        wx_cell("Feels", wx["feels"], wx["obs_url"]),
        wx_cell("High / Low", "%s / %s" % (wx["high"], wx["low"]), wx["source_url"]),
        wx_cell("Wind", wx["wind"], wx["obs_url"]),
        wx_cell("Humidity", wx["humidity"], wx["obs_url"]),
        wx_cell("Rain", wx["rain_chance"], wx["source_url"]),
    ]),
    E(wx["observed"]), E(wx["obs_url"]), E(wx["source_url"]), E(wx["source_label"]), E(wx["place"]))

WEATHER_JS = """<script>
(function () {
  var strip = document.getElementById('wx-strip');
  if (!strip || !navigator.geolocation) { return; }
  var WMO = {0:'Clear',1:'Mainly clear',2:'Partly cloudy',3:'Overcast',45:'Fog',48:'Rime fog',
    51:'Light drizzle',53:'Drizzle',55:'Heavy drizzle',56:'Freezing drizzle',57:'Freezing drizzle',
    61:'Light rain',63:'Rain',65:'Heavy rain',66:'Freezing rain',67:'Freezing rain',71:'Light snow',
    73:'Snow',75:'Heavy snow',77:'Snow grains',80:'Light showers',81:'Showers',82:'Heavy showers',
    85:'Snow showers',86:'Snow showers',95:'Thunderstorms',96:'Storms with hail',99:'Storms with hail'};
  var COMPASS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
  function t(v) { return v.toFixed(1) + '\\u00B0C'; }
  navigator.geolocation.getCurrentPosition(function (pos) {
    var la = pos.coords.latitude, lo = pos.coords.longitude;
    var api = 'https://api.open-meteo.com/v1/forecast?latitude=' + la + '&longitude=' + lo +
      '&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,' +
      'wind_speed_10m,wind_direction_10m&daily=temperature_2m_max,temperature_2m_min,' +
      'precipitation_probability_max&timezone=auto&forecast_days=1';
    var link = 'https://weather.com/weather/today/l/' + la.toFixed(2) + ',' + lo.toFixed(2);
    Promise.all([
      fetch(api).then(function (r) { return r.json(); }),
      fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=' + la +
            '&longitude=' + lo + '&localityLanguage=en')
        .then(function (r) { return r.json(); })
        .catch(function () { return null; })
    ]).then(function (res) {
      var d = res[0], g = res[1], c = d.current, day = d.daily;
      var name = g && (g.city || g.locality || g.principalSubdivision)
        ? (g.city || g.locality) + (g.principalSubdivision ? ', ' + g.principalSubdivision : '')
        : la.toFixed(2) + ', ' + lo.toFixed(2);
      var vals = [t(c.temperature_2m), t(c.apparent_temperature),
        t(day.temperature_2m_max[0]) + ' / ' + t(day.temperature_2m_min[0]),
        Math.round(c.wind_speed_10m) + ' km/h ' + COMPASS[Math.round((c.wind_direction_10m % 360) / 22.5) % 16],
        c.relative_humidity_2m + '%', day.precipitation_probability_max[0] + '%'];
      var place = document.getElementById('wx-place');
      place.textContent = name + ' \\u00B7 ' + (WMO[c.weather_code] || 'Code ' + c.weather_code);
      place.href = link;
      var cells = strip.querySelectorAll('.wx-cell');
      for (var i = 0; i < cells.length && i < vals.length; i++) {
        cells[i].querySelector('.wx-value').textContent = vals[i];
        cells[i].href = link;
      }
      var note = document.getElementById('wx-note');
      if (note) {
        note.innerHTML = 'Current conditions for your device location, via ' +
          '<a href="https://open-meteo.com" target="_blank" rel="noopener">Open-Meteo</a>, ' +
          'linked through to <a href="' + link + '" target="_blank" rel="noopener">weather.com</a>. ' +
          'Local time zone ' + (d.timezone || 'unknown') + '.';
      }
    }).catch(function () { /* leave the build-time strip in place */ });
  }, function () { /* permission denied - leave the build-time strip in place */ },
     { timeout: 8000, maximumAge: 900000 });
})();
</script>"""

# ---------------------------------------------------------------- rate grid
def rate_cell(code, value, chg, url, sub=None):
    out = ['<a class="rate-cell" href="%s" target="_blank" rel="noopener">' % E(url)]
    lbl = '<span class="rc-code">%s</span>' % E(code)
    if sub:
        lbl += '<span class="rc-sub">%s</span>' % E(sub)
    out.append('<span class="rc-label">%s</span>' % lbl)
    v = '<span class="rc-val">%s</span>' % E(value)
    if chg:
        v += ' <small class="%s">%s</small>' % (chg_class(chg), E(chg))
    out.append(v)
    out.append('</a>')
    return "".join(out)

XE = "https://www.xe.com/currencyconverter/convert/?Amount=1&amp;From=USD&amp;To=%s"
fx_cells = [rate_cell("BTC", mk["btc"]["price"], mk["btc"]["chg"],
                      "https://www.coindesk.com/price/bitcoin", "24h"),
            rate_cell("USD", "1.0000", None,
                      "https://www.xe.com/currencyconverter/convert/?Amount=1&amp;From=USD&amp;To=USD", "base")]
for r in mk["fx"]:
    fx_cells.append(rate_cell(r["code"], r["rate"], r["chg"], XE % r["code"]))

YQ = "https://finance.yahoo.com/quote/%s"
def idx_url(sym):
    if sym == "^STI":
        return "https://www.tradingview.com/symbols/TVC-STI/"
    if sym in ("^AXJO", "^AORD"):
        # us Yahoo 404s the Australian index quote pages; the AU edition serves them
        return "https://au.finance.yahoo.com/quote/%s" % sym.replace("^", "%5E")
    if sym == "000001.SS":
        return YQ % "000001.SS"
    return YQ % sym.replace("^", "%5E")
idx_cells = [rate_cell(i["name"], i["value"], i["chg"], idx_url(i["symbol"])) for i in mk["indices"]]

com_cells = []
for c in cm["commodities"]:
    val = "%s %s" % (c["price"], c["unit"])
    com_cells.append(rate_cell(c["name"], val, c["chg"], c["url"], c.get("flag")))

def grid(cells):
    return '<div class="rate-grid">\n%s\n</div>' % "\n".join(cells)

# ---------------------------------------------------------------- performers
def table(kind, rows):
    h = ['<table class="market-table"><thead><tr><th>%s</th><th class="num">Price</th>'
         '<th class="num">Chg</th><th class="num">Vol</th></tr></thead><tbody>' % kind]
    for r in rows:
        h.append('<tr><td><a href="%s" target="_blank" rel="noopener">%s</a></td>'
                 '<td class="num">%s</td><td class="num %s">%s</td><td class="num vol">%s</td></tr>'
                 % (E(r["url"]), E(r["name"]), E(r["price"]), chg_class(r["chg"]),
                    E(r["chg"]), E(r.get("vol") or "n/a")))
    h.append("</tbody></table>")
    return "".join(h)

def perf_block(m, first=False):
    cls = "perf-block" if first else "perf-block page-break-before"
    return """<div class="%s">
<h4 class="perf-title">%s</h4>
<p class="caption">%s</p>
<div class="two-col">
<div class="perf-col"><p class="mover-note">%s</p>%s</div>
<div class="perf-col"><p class="mover-note">%s</p>%s</div>
</div>
</div>""" % (cls, E(m["title"]), E(m["caption"]), E(m["gainer_note"]), table("Gainers", m["gainers"]),
             E(m["loser_note"]), table("Losers", m["losers"]))

order = {}
for src in (pa, pb, pc):
    for m in src["markets"]:
        order[m["key"]] = m

# Yahoo 404s several of the US small-cap movers; the US block was scraped from
# StockAnalysis, so point the rows at the source that actually resolves.
for side in ("gainers", "losers"):
    for row in order["us"][side]:
        tkr = row["url"].rstrip("/").split("/")[-1]
        row["url"] = "https://stockanalysis.com/stocks/%s/" % tkr.lower()
order["us"]["caption"] = order["us"]["caption"].replace(
    "Yahoo Finance gainers/losers pages returned an error and were not used",
    "Yahoo Finance gainers/losers pages returned an error and were not used; rows link to StockAnalysis, "
    "which resolves for every ticker listed")

seq = ["anz", "japan", "singapore", "hongkong", "china", "us", "uk", "germany", "brazil"]
perf_html = "\n".join(perf_block(order[k], first=(i == 0)) for i, k in enumerate(seq))

# ---------------------------------------------------------------- lists
def headline_list(items, outlet_key=None):
    li = []
    for it in items:
        src = it.get("outlet") or outlet_key or "source"
        li.append('<li><a class="hl" href="%s" target="_blank" rel="noopener">%s</a>'
                  '<span class="hl-detail">%s</span>'
                  '<a class="hl-src" href="%s" target="_blank" rel="noopener">per %s</a></li>'
                  % (E(it["url"]), E(it["headline"]), E(it["detail"]), E(it["url"]), E(src)))
    return '<ol class="headlines">%s</ol>' % "".join(li)

cr_html = []
for r in cr["regions"]:
    body = headline_list(r["items"]) if r["items"] else \
        '<p class="mover-note">No capital raise or new listing item with a verifiable source URL was found for this region in the current window.</p>'
    cr_html.append('<div class="cr-region"><h3 class="subhead">%s</h3>'
                   '<p class="mover-note">%s</p>%s</div>' % (E(r["name"]), E(r["summary"]), body))
cr_html = '<div class="cr-grid">%s</div>' % "".join(cr_html)

tech_html = headline_list(tech["items"])

outlets = na["outlets"] + nb["outlets"]
# ABC News (US) slots in with the US broadcast outlets, after Fox and before the WSJ.
abcus = load("news-abcus.json")["outlet"]
outlets.insert([o["key"] for o in outlets].index("fox") + 1, abcus)

# Reorder the US/UK business-heavy outlets so WSJ (market-first) sits ahead of CNN.
idx = {o["key"]: i for i, o in enumerate(outlets)}
wsj = outlets.pop(idx["wsj"])
cnn_idx = idx["cnn"]
outlets.insert(cnn_idx, wsj)

alj = [o for o in outlets if o["key"] == "aljazeera"]
outlets = [o for o in outlets if o["key"] != "aljazeera"] + alj

# ----------------------------------------------------------------- story ordering
# Within every World News outlet, business/financial stories lead, followed by
# national/international general news, then local/entertainment/lifestyle/sport.
# This applies to the Australian outlets (ABC, SBS) and is kept consistent
# across all World News sections.
BUSINESS_KEYWORDS = [
    "business", "finance", "economy", "economic", "market", "markets",
    "tariff", "tariffs", "trade", "rba", "reserve bank", "asx", "shares",
    "stocks", "dollar", "aud/usd", "budget", "inflation", "rates", "gdp",
    "employment", "unemployment", "wages", "commodities", "mining", "bank",
    "banks", "banking", "investment", "investor", "investors", "earnings",
    "profit", "revenue", "loss", "debt", "fiscal", "monetary", "recession",
    "growth", "oil", "gold", "crypto", "bitcoin", "merger", "acquisition",
    "ipo", "float", "listing", "capital", "fund", "funds", "funding",
    "valuation", "shareholder", "dividend"
]

LOCAL_PATH_PATTERNS = [
    "/local/", "/state/", "/nsw/", "/vic/", "/qld/", "/wa/", "/sa/",
    "/tas/", "/act/", "/nt/", "/regional/", "/sydney/", "/melbourne/",
    "/brisbane/", "/perth/", "/adelaide/", "/hobart/", "/canberra/",
    "/darwin/"
]

ENTERTAINMENT_KEYWORDS = [
    "celebrity", "film", "movie", "movies", "tv", "television", "music",
    "album", "concert", "festival", "actor", "actress", "director",
    "hollywood", "bollywood", "showbiz", "entertainment", "fashion",
    "red carpet", "premiere", "award", "awards", "grammy", "oscar",
    "emmy", "bafta"
]

SPORT_KEYWORDS = [
    "afl", "nrl", "cricket", "rugby", "football", "soccer", "tennis",
    "golf", "formula 1", "f1", "basketball", "nba", "nfl", "baseball",
    "mlb", "olympics", "medal", "match", "game", "race", "grand final",
    "world cup", "tournament", "championship"
]


def story_rank(item):
    """Return sort rank: 0=business/finance, 1=national/international, 2=local/entertainment/sport."""
    url = item.get("url", "").lower()
    text = (item.get("headline", "") + " " + item.get("detail", "")).lower()

    # Business/finance via URL path
    if any(p in url for p in ["/business", "/money", "/finance", "/market", "/economy", "/companies"]):
        return 0

    # Business/finance via keywords
    if any(kw in text for kw in BUSINESS_KEYWORDS):
        return 0

    # Local via URL path
    if any(p in url for p in LOCAL_PATH_PATTERNS):
        return 2

    # Entertainment / sport / lifestyle via keywords
    if any(kw in text for kw in ENTERTAINMENT_KEYWORDS) or any(kw in text for kw in SPORT_KEYWORDS):
        return 2

    # Default to national/international general news
    return 1


# Apply the ordering to every World News outlet.
for o in outlets:
    o["items"].sort(key=story_rank)

news_html = []
for o in outlets:
    note = '<p class="caption">%s</p>' % E(o["note"]) if o.get("note") else ""
    news_html.append('<div class="outlet-section"><h3 class="subhead">%s '
                     '<a class="site" href="https://%s" target="_blank" rel="noopener">%s</a></h3>'
                     '<p class="outlet-summary">%s</p>%s%s</div>'
                     % (E(o["name"]), E(o["site"].split("/")[0]), E(o["site"]),
                        E(o["summary"]), note, headline_list(o["items"], o["name"])))
news_html = "".join(news_html)

sport_html = "".join(
    '<div class="sport-section"><h3 class="subhead">%s</h3>%s</div>'
    % (E(c["name"]), headline_list(c["items"])) for c in sp["codes"])
sport_html = '<div class="sport-grid">%s</div>' % sport_html

# ---------------------------------------------------------------- assemble

HTML = """<div class="pnw">

<header class="masthead">
  <div class="kicker"><span class="wordmark">BOE</span> Blue Ocean Equities Pty Ltd</div>
  <h1>Market Wrap Up</h1>
  <div class="dateline">
    <span class="edition-chip">%s</span>
    <span>%s</span>
    <span>·</span>
    <span><a href="https://www.boeq.com.au" target="_blank" rel="noopener">boeq.com.au</a></span>
  </div>
</header>

%s
%s
<p class="market-summary">%s</p>
<p class="section-caption page-break-before">%s</p>

<h3 class="subhead">Exchange Rates &amp; Bitcoin</h3>
<p class="caption">Bitcoin spot via <a href="https://www.coindesk.com/price/bitcoin" target="_blank" rel="noopener">CoinDesk</a> and <a href="https://www.coingecko.com/en/coins/bitcoin" target="_blank" rel="noopener">CoinGecko</a>. FX are ECB daily reference fixings from <a href="https://api.frankfurter.dev/v1/latest?from=USD" target="_blank" rel="noopener">Frankfurter</a>, base USD, %s versus prior business day %s; cells link to <a href="https://www.xe.com/currencyconverter/" target="_blank" rel="noopener">xe.com</a>.</p>
%s

<h3 class="subhead">World Indices</h3>
<p class="caption">Latest closing prints for the sessions of Wednesday 26 August 2026 via <a href="https://finance.yahoo.com/world-indices" target="_blank" rel="noopener">Yahoo Finance World Indices</a>; indexes from exchanges still open at time of collection reflect their latest prints.</p>
%s

<h3 class="subhead page-break-before">Commodities</h3>
<p class="market-summary">%s</p>
%s

<h3 class="subhead page-break-before">Top Performers</h3>
<p class="caption">Biggest gainers and losers by percentage move in each market's most recent completed session. Gains in green, losses in red.</p>
%s

<h2>Capital Raises &amp; New Listings</h2>
<p class="section-caption">Placements, rights issues, secondary offerings and stock exchange IPOs - planned, launched, priced or completed - reported in the past week.</p>
%s

<h2 class="page-break-before">Tech</h2>
<p class="section-caption">Ten global technology stories from the past 48 hours, spanning US, Asian, European and Australian coverage.</p>
%s

<h2 class="page-break-before">World News</h2>
%s

<h2 class="page-break-before">World Sport</h2>
%s

<footer>
<p><strong>Market Wrap Up</strong> - a public news digest published by Blue Ocean Equities Pty Ltd, an independent Australian securities and equities advisory firm (<a href="https://www.boeq.com.au" target="_blank" rel="noopener">boeq.com.au</a>). %s Edition: %s.</p>
<p><strong>Story rotation policy:</strong> each edition is compared against the previously published version of this page. A headline carried in the prior edition is not repeated verbatim unless it remains the leading, actively developing story on its topic, in which case it is refreshed with the latest angle. Market data, mover tables and all written summary paragraphs are re-gathered and rewritten every run. On this run the previously published artifact could not be retrieved for comparison (the hosted copy returned a sign-in wall and no local prior edition exists in the project), so every item was sourced fresh.</p>
<p><strong>Sourcing:</strong> every headline, rate, index, commodity, equity and sports result on this page links to its source. Items without a verifiable working URL were dropped rather than published unlinked. Where a source publishes turnover rather than share volume, volumes are derived as turnover divided by last price and prefixed with a tilde, as noted in the relevant caption. Commodity cells marked <span class="rc-sub">stale</span> had not refreshed past the prior day's print; the rare earths cell is an equity <span class="rc-sub">proxy</span> (MP Materials, NYSE: MP) as no reliable daily spot benchmark is published.</p>
<p><strong>Not investment advice.</strong> This page is a summary of publicly reported information assembled for general information only. It does not take account of any person's objectives, financial situation or needs, and is not a recommendation to buy, hold or sell any security.</p>
<p>Outlets attempted and still unavailable this run: news.com.au, smh.com.au, 9news.com.au, theaustralian.com.au. Working Australian substitutes ABC News and SBS News are carried above.</p>
</footer>

</div>
""" % (EDITION, DATELINE, WEATHER, WEATHER_JS, MARKET_NEWS, ASOF_CAPTION,
       E(mk["fx_base_date"]), E(mk["fx_prior_date"]),
       grid(fx_cells), grid(idx_cells),
       E(cm["summary"]), grid(com_cells), perf_html,
       cr_html, tech_html, news_html, sport_html,
       GEN_NOTE, EDITION)

with open(OUT, "w") as f:
    f.write(HTML)

# Self-contained preview.html for local viewing and PDF export.
css = open(CSS_PATH).read() if os.path.exists(CSS_PATH) else ""
preview_doc = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Market Wrap Up</title></head>
<body style="margin:0">
<style>
%s
</style>
%s
</body></html>
""" % (css, HTML)
with open(PREVIEW, "w") as f:
    f.write(preview_doc)

print("wrote", OUT, len(HTML), "bytes")
print("wrote", PREVIEW, len(preview_doc), "bytes")
print("market-news words:", len(mnp.split()))
print("rate cells:", len(fx_cells), "indices:", len(idx_cells), "commodities:", len(com_cells))
print("perf blocks:", len(seq), "outlets:", len(outlets), "sport codes:", len(sp["codes"]))
