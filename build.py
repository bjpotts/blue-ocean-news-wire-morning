#!/usr/bin/env python3
"""Build the Market Wrap Up digest page for Blue Ocean Equities Pty Ltd."""
import json, html, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "digest.html")
PREVIEW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview.html")
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "style.css")

# Captured before OUT is overwritten below, so the footer's rotation note can
# state honestly whether a prior local edition existed to compare against.
HAD_PREVIOUS_EDITION = os.path.exists(OUT)

MAX_AGE_HOURS = int(os.environ.get("MAX_DATA_AGE_HOURS", "36"))

def load(n):
    with open(os.path.join(D, n)) as f:
        return json.load(f)

def _data_age_hours(path):
    if not os.path.exists(path):
        return float("inf")
    mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=ZoneInfo("Australia/Sydney"))
    now = datetime.now(ZoneInfo("Australia/Sydney"))
    return (now - mtime).total_seconds() / 3600.0

def _check_freshness():
    required = {
        "markets.json": "Exchange rates, Bitcoin and world indices",
        "commodities.json": "Commodity prices",
        "perf-a.json": "Top performers (region set A)",
        "perf-b.json": "Top performers (region set B)",
        "perf-c.json": "Top performers (region set C) and market news summary",
        "capraises.json": "Capital raises and new listings",
        "earnings.json": "Market earnings reporting",
        "tech.json": "Technology news",
        "news-a.json": "World news (set A)",
        "news-b.json": "World news (set B)",
        "news-abcus.json": "World news (ABC News US)",
        "guardian.json": "World news (The Guardian editions)",
        "sport.json": "World sport",
        "weather.json": "Weather",
    }
    if MAX_AGE_HOURS <= 0:
        # Documented escape hatch for manual/forced runs: a non-positive limit
        # disables the guard entirely rather than treating every file as stale.
        print("NOTE: data freshness guard disabled via MAX_DATA_AGE_HOURS.",
              file=sys.stderr)
        return
    stale = []
    for filename, description in required.items():
        age = _data_age_hours(os.path.join(D, filename))
        if age > MAX_AGE_HOURS:
            stale.append((filename, description, age))
    if stale:
        print("ERROR: stale data detected; refusing to build.", file=sys.stderr)
        for filename, description, age in stale:
            print(f"  - {filename} ({description}): {age:.1f} hours old (limit {MAX_AGE_HOURS}h)", file=sys.stderr)
        print("Run the data fetch scripts before building, or set MAX_DATA_AGE_HOURS=0 to disable this guard for a forced run.", file=sys.stderr)
        sys.exit(1)

_check_freshness()

mk = load("markets.json")
cm = load("commodities.json")
pa = load("perf-a.json")
pb = load("perf-b.json")
pc = load("perf-c.json")
cr = load("capraises.json")
eg = load("earnings.json")
tech = load("tech.json")
na = load("news-a.json")
nb = load("news-b.json")
sp = load("sport.json")
wx = load("weather.json")
cfg = load("config.json")


def _check_performers_fresh(*sources):
    """Every gainers/losers region must have been re-pulled by this run.

    fetch_performers.py stamps each region with the time it was fetched and
    flags any region it had to carry over from a previous run. Publishing a
    carried-over region would present an earlier session's movers as today's,
    so the build stops instead.
    """
    if MAX_AGE_HOURS <= 0:
        return
    now = datetime.now(ZoneInfo("Australia/Sydney"))
    stale = []

    def _age_problem(label, block):
        fetched = block.get("fetched")
        if block.get("stale") or not fetched:
            return "%s (not refreshed this run)" % label
        try:
            age = (now - datetime.fromisoformat(fetched)).total_seconds() / 3600
        except ValueError:
            return "%s (unreadable fetch timestamp)" % label
        if age > MAX_AGE_HOURS:
            return "%s (%.1f hours old, limit %dh)" % (label, age, MAX_AGE_HOURS)
        return None

    for src in sources:
        mn = src.get("market_news")
        if mn is not None:
            problem = _age_problem("Market News opening paragraph", mn)
            if problem:
                stale.append(problem)
        for market in src.get("markets", []):
            problem = _age_problem(market.get("title", market.get("key", "?")), market)
            if problem:
                stale.append(problem)

    if stale:
        print("ERROR: market sections are not current; refusing to build.",
              file=sys.stderr)
        for line in stale:
            print("  - %s" % line, file=sys.stderr)
        print("Re-run fetch_markets.py then fetch_performers.py so every region "
              "and the Market News paragraph are pulled for the current session.",
              file=sys.stderr)
        sys.exit(1)


_check_performers_fresh(pa, pb, pc)

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
cfg = load("config.json")

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

def _apply_dedup_rules(rules):
    for region_key, rule in rules.get("capital_raises", {}).items():
        region = _region(region_key)
        if region is None:
            continue
        for ext in rule.get("extend", []):
            _extend(region["items"], ext["needle"], ext["clause"])
        for drop in rule.get("drop", []):
            region["items"] = _drop(region["items"], drop)
        region["items"] += bf.get(f"{region_key}_items", [])
        # Summaries are not backfilled: fetch_capraises.py regenerates one every
        # run from that run's own items, and a hardcoded override here would
        # silently freeze the paragraph forever (it did - see CHANGELOG) and
        # can drift out of sync with a since-emptied items list.

    for code_key, rule in rules.get("sport", {}).items():
        code = next((c for c in sp["codes"] if c["key"] == code_key), None)
        if code is None:
            continue
        for drop in rule.get("drop", []):
            code["items"] = _drop(code["items"], drop)

    for outlet_key, rule in rules.get("news", {}).items():
        outlet = next((o for o in na["outlets"] if o["key"] == outlet_key), None)
        if outlet is None:
            continue
        for drop in rule.get("drop", []):
            outlet["items"] = _drop(outlet["items"], drop)
        _bf_item = bf.get(f"{outlet_key}_item") or {}
        if isinstance(_bf_item, dict) and _bf_item.get("url"):
            outlet["items"].append(_bf_item)

_apply_dedup_rules(cfg.get("dedup_rules", {}))

ew = cfg["edition_window"]
br = cfg["brand"]
secs = {s["key"]: s for s in cfg["sections"]}

def _sydney_now():
    return datetime.now(ZoneInfo(ew["timezone"]))

_now = _sydney_now()
_hr = _now.hour
# Scheduled runs derive the edition from the Sydney clock. A manual run
# outside the normal window can set EDITION_OVERRIDE so the masthead
# matches the edition actually being produced.
_auto_edition = "Morning Edition" if ew["morning_start_hour"] <= _hr < ew["morning_end_hour"] else "Evening Edition"
EDITION = os.environ.get("EDITION_OVERRIDE", "").strip() or _auto_edition
_DATELINE_DATE = _now.strftime("%A %d %B %Y")
_DATELINE_TIME = _now.strftime("%H:%M AEST")
_DATELINE_UTC = _now.astimezone(ZoneInfo("UTC")).strftime("%H:%M UTC")
_DATELINE_LOC = ew["location"]
DATELINE = f"{EDITION} \u00b7 {_DATELINE_DATE} \u00b7 {_DATELINE_TIME} \u00b7 {_DATELINE_LOC}"
GEN_NOTE = f"Generated {_DATELINE_DATE} at {_DATELINE_TIME} / {_DATELINE_UTC}."

def chg_class(c):
    c = (c or "").strip()
    # U+2212 is what TradingView renders; treating it as flat would colour a
    # genuine loss as unchanged.
    if c.startswith("-") or c.startswith("\u2212"):
        return "chg-neg"
    if c.startswith("+"):
        return "chg-pos"
    return "chg-flat"

# ---------------------------------------------------------------- market news
# The paragraph is generated from live index/FX/bitcoin data on every run, so no
# text substitutions are applied to it here.
MARKET_NEWS = E(pc["market_news"]["paragraph"])
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

XE = cfg["currency_grid"]["base_url"]
fx_cells = [rate_cell("BTC", mk["btc"]["price"], mk["btc"]["chg"],
                      cfg["currency_grid"]["btc_url"], cfg["currency_grid"]["btc_sub"]),
            rate_cell("USD", "1.0000", None,
                      XE % "USD", cfg["currency_grid"]["usd_sub"])]
for r in mk["fx"]:
    fx_cells.append(rate_cell(r["code"], r["rate"], r["chg"], XE % r["code"]))

idx_cfg = cfg["indices_grid"]
YQ = idx_cfg["yahoo_quote_url"]
def idx_url(sym):
    # A few indices have live Yahoo data but no Yahoo quote page, so they link
    # to their TradingView symbol page instead of a URL that 404s.
    if sym in idx_cfg["tradingview_quote_urls"]:
        return idx_cfg["tradingview_quote_urls"][sym]
    if sym == "^STI":
        return idx_cfg["stai_quote_url"]
    # Yahoo's US edition 404s on the Australasian indices; its AU edition serves
    # all three.
    if sym in ("^AXJO", "^AORD", "^NZ50"):
        return idx_cfg["au_yahoo_quote_url"] % sym.replace("^", "%5E")
    if sym == "000001.SS":
        return YQ % "000001.SS"
    return YQ % sym.replace("^", "%5E")
idx_cells = [rate_cell(i["name"], i["value"], i["chg"], idx_url(i["symbol"]), i.get("flag"))
             for i in mk["indices"]]

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

def sourced_para(text, sources):
    """A paragraph with its supporting article cited as a working link."""
    h = E(text)
    if sources:
        s = sources[0]
        h += ' <a href="%s">%s</a>.' % (E(s["url"]), E(s["title"]))
    return h

def rotation_note(cr, eg, had_previous):
    """Story-rotation status for the footer, computed from this run's actual
    fresh-vs-repeated counts (fetch_capraises.py/fetch_earnings.py) rather
    than a fixed claim baked into the template."""
    regions = cr["regions"] + eg["regions"]
    total = sum(len(r["items"]) for r in regions)
    fresh = sum(r.get("fresh_count", 0) for r in regions)
    repeated = total - fresh
    if not had_previous:
        basis = ("No previous local edition of this project existed before "
                 "this run, so every item was necessarily sourced fresh.")
    elif total == 0:
        basis = ("No rotation-tracked items were available to compare this "
                 "run.")
    else:
        basis = ("Of the %d Capital Raises and Market Earnings Reports "
                 "items carried this run, %d are newly sourced since the "
                 "last local build and %d repeat a still-current item "
                 "because no fresher verified source was found for that "
                 "region." % (total, fresh, repeated))
    return ("Each edition's Capital Raises and Market Earnings Reports "
            "items are compared against the last local build's linked "
            "items (not a live re-fetch of the previously published page). "
            "%s World News, Tech and World Sport headlines are pulled fresh "
            "from live feeds every run, though they are not currently "
            "checked against the prior edition's exact wording. Market "
            "data, mover tables and all written summary paragraphs are "
            "re-gathered and rewritten every run." % basis)


def blocked_outlets_note(nb, substitutes):
    """Footer line for historically-blocked AU outlets, sourced from this
    run's real retry (fetch_news.py's check_blocked_outlets), not a fixed
    list assumed to still be accurate."""
    blocked = nb.get("blocked", [])
    if not blocked:
        return ("All previously-blocked Australian outlets responded "
                "successfully when re-attempted this run.")
    return ("Outlets attempted and still unavailable this run: %s. Working "
            "Australian substitutes %s are carried above."
            % (", ".join(blocked), substitutes))


def perf_block(m, first=False):
    cls = "perf-block" if first else "perf-block page-break-before"
    return """<div class="%s">
<h4 class="perf-title">%s</h4>
<p class="caption">%s</p>
<div class="two-col">
<div class="perf-col"><p class="mover-note">%s</p>%s</div>
<div class="perf-col"><p class="mover-note">%s</p>%s</div>
</div>
</div>""" % (cls, E(m["title"]), E(m["caption"]),
             sourced_para(m["gainer_note"], m.get("gainer_note_sources")),
             table("Gainers", m["gainers"]),
             sourced_para(m["loser_note"], m.get("loser_note_sources")),
             table("Losers", m["losers"]))

order = {}
for src in (pa, pb, pc):
    for m in src["markets"]:
        order[m["key"]] = m

# Yahoo 404s several of the US small-cap movers; the US block was scraped from
# StockAnalysis, so point the rows at the source that actually resolves.
us_rewrite = cfg.get("us_performers_url_rewrite", {})
if us_rewrite.get("enabled"):
    for side in ("gainers", "losers"):
        for row in order["us"][side]:
            tkr = row["url"].rstrip("/").split("/")[-1]
            row["url"] = us_rewrite["template"] % tkr.lower()
    order["us"]["caption"] = order["us"]["caption"].replace(
        us_rewrite["caption_search"],
        us_rewrite["caption_search"] + us_rewrite.get("caption_append", ""))

seq = cfg["performers_sequence"]
_perf_blocks = [perf_block(order[k], first=(i == 0)) for i, k in enumerate(seq)]

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
    # r["summary"] already states plainly when nothing verifiable was found
    # for this region this run, so no separate fallback paragraph is needed.
    body = headline_list(r["items"]) if r["items"] else ""
    cr_html.append('<div class="cr-region"><h3 class="subhead">%s</h3>'
                   '<p class="mover-note">%s</p>%s</div>' % (E(r["name"]), E(r["summary"]), body))
cr_html = '<div class="cr-grid">%s</div>' % "".join(cr_html)

earnings_by_region = {}
for r in eg["regions"]:
    if not r["items"]:
        # A region with nothing verifiable is dropped entirely rather than
        # rendering an empty "no reports" block under a live performer region.
        continue
    earnings_by_region[r["key"]] = (
        '<div class="cr-region market-earnings-block page-break-before" '
        'data-earnings-region="%s"><h3 class="subhead">%s — %s</h3>'
        '<p class="caption">%s</p><p class="mover-note">%s</p>%s</div>'
        % (E(r["key"]), E(secs["market_earnings"]["heading"]), E(r["name"]),
           E(secs["market_earnings"]["caption"]), E(r["summary"]), headline_list(r["items"])))

earnings_after_performer = {
    "anz": "anz",
    "china": "asia",
    "us": "us",
    "uk": "uk",
    "germany": "europe",
    "brazil": "rest",
}
perf_earnings_html = []
for key, block in zip(seq, _perf_blocks):
    perf_earnings_html.append(block)
    earnings_key = earnings_after_performer.get(key)
    if earnings_key and earnings_key in earnings_by_region:
        perf_earnings_html.append(earnings_by_region[earnings_key])
perf_earnings_html = "\n".join(perf_earnings_html)

tech_html = ('<div class="sport-section"><h3 class="subhead">Global Technology</h3>%s</div>'
             % headline_list(tech["items"]))

outlets = na["outlets"] + nb["outlets"]
# ABC News (US) slots in with the US broadcast outlets, after Fox and before the WSJ.
abcus = load("news-abcus.json")["outlet"]
outlets.insert([o["key"] for o in outlets].index("fox") + 1, abcus)

# Apply configurable outlet reordering.
oo = cfg.get("outlet_ordering", {})
for pair in oo.get("reorder_pairs", []):
    if pair["key"] in [o["key"] for o in outlets] and pair["before_key"] in [o["key"] for o in outlets]:
        idx_map = {o["key"]: i for i, o in enumerate(outlets)}
        moving = outlets.pop(idx_map[pair["key"]])
        target_idx = idx_map[pair["before_key"]]
        if idx_map[pair["key"]] > target_idx:
            outlets.insert(target_idx, moving)
        else:
            outlets.insert(target_idx, moving)

for key in oo.get("move_to_end", []):
    outlets = [o for o in outlets if o["key"] != key] + [o for o in outlets if o["key"] == key]

# The Guardian's five regional editions slot into their matching regional groups.
if os.path.exists(os.path.join(D, "guardian.json")):
    gd = {o["key"]: o for o in load("guardian.json")["outlets"]}
    def _after(key):
        return [o["key"] for o in outlets].index(key) + 1
    for ins in oo.get("guardian_insertions", []):
        gk, after = ins["edition_key"], ins["after_key"]
        if gk in gd and any(o["key"] == after for o in outlets):
            outlets.insert(_after(after), gd[gk])

# ----------------------------------------------------------------- story ordering
# Within every World News outlet, business/financial stories lead, followed by
# national/international general news, then local/entertainment/lifestyle/sport.
# This applies to the Australian outlets (ABC, SBS) and is kept consistent
# across all World News sections.
sr = cfg.get("story_ranking", {})
BUSINESS_URL_PATHS = sr.get("business_url_paths", [])
BUSINESS_KEYWORDS = sr.get("business_keywords", [])
LOCAL_URL_PATHS = sr.get("local_url_paths", [])
ENTERTAINMENT_KEYWORDS = sr.get("entertainment_keywords", [])
SPORT_KEYWORDS = sr.get("sport_keywords", [])


def story_rank(item):
    """Return sort rank: 0=business/finance, 1=national/international, 2=local/entertainment/sport."""
    url = item.get("url", "").lower()
    text = (item.get("headline", "") + " " + item.get("detail", "")).lower()

    if any(p in url for p in BUSINESS_URL_PATHS):
        return 0

    if any(kw in text for kw in BUSINESS_KEYWORDS):
        return 0

    if any(p in url for p in LOCAL_URL_PATHS):
        return 2

    if any(kw in text for kw in ENTERTAINMENT_KEYWORDS) or any(kw in text for kw in SPORT_KEYWORDS):
        return 2

    return 1


# Apply the ordering to every World News outlet.
for o in outlets:
    o["items"].sort(key=story_rank)

news_html = []
for o in outlets:
    note = '<p class="caption">%s</p>' % E(o["note"]) if o.get("note") else ""
    news_html.append('<div class="outlet-section"><h3 class="subhead">%s '
                     '<a class="site" href="%s" target="_blank" rel="noopener">%s</a></h3>'
                     '<p class="outlet-summary">%s</p>%s%s</div>'
                     % (E(o["name"]), E(("https://" + o["site"]) if o["key"].startswith("g") else "https://" + o["site"].split("/")[0]), E(o["site"]),
                        E(o["summary"]), note, headline_list(o["items"], o["name"])))
news_html = "".join(news_html)
news_html = '<div class="news-grid">%s</div>' % news_html

sport_html = "".join(
    '<div class="sport-section"><h3 class="subhead">%s</h3>%s</div>'
    % (E(c["name"]), headline_list(c["items"])) for c in sp["codes"])
sport_html = '<div class="sport-grid">%s</div>' % sport_html

# ---------------------------------------------------------------- assemble

HTML = """<div class="pnw">

<header class="masthead">
  <div class="kicker"><span class="wordmark">%s</span> %s</div>
  <h1>%s</h1>
  <div class="dateline">
    <span class="edition-chip">%s</span>
    <span>%s</span>
    <span>·</span>
    <span><a href="%s" target="_blank" rel="noopener">%s</a></span>
  </div>
</header>

%s
%s
<p class="market-summary">%s</p>
<p class="section-caption %s">%s</p>

<h3 class="subhead">%s</h3>
<p class="caption">%s</p>
%s

<h3 class="subhead %s">%s</h3>
<p class="caption">%s</p>
%s

<h3 class="subhead %s">%s</h3>
<p class="market-summary">%s</p>
%s

<h3 class="subhead %s">%s</h3>
<p class="caption">%s</p>
%s

<h2>%s</h2>
<p class="section-caption">%s</p>
%s

<h2 class="page-break-before">%s</h2>
%s

<h2 class="page-break-before">%s</h2>
%s

<h2 class="page-break-before">%s</h2>
%s

<footer>
<p><strong>%s</strong> - a public news digest published by %s, an independent Australian securities and equities advisory firm (<a href="%s" target="_blank" rel="noopener">%s</a>). %s Edition: %s.</p>
<p><strong>Story rotation policy:</strong> a headline carried in the prior edition is not repeated verbatim unless it remains the leading, actively developing story on its topic, in which case it is refreshed with the latest angle. %s</p>
<p><strong>Sourcing:</strong> every headline, rate, index, commodity, equity and sports result on this page links to its source. Items without a verifiable working URL were dropped rather than published unlinked. Where a source publishes turnover rather than share volume, volumes are derived as turnover divided by last price and prefixed with a tilde, as noted in the relevant caption. Commodity cells marked <span class="rc-sub">stale</span> had not refreshed past the prior day's print; the rare earths cell is an equity <span class="rc-sub">proxy</span> (MP Materials, NYSE: MP) as no reliable daily spot benchmark is published.</p>
<p><strong>Not investment advice.</strong> %s</p>
<p>%s</p>
</footer>

</div>
""" % (
    E(br["wordmark"]), E(br["company"]), E(br["name"]), EDITION, DATELINE,
    E(br["site_url"]), E(br["site"]),
    WEATHER, WEATHER_JS, MARKET_NEWS,
    "page-break-before" if secs["market_news"].get("page_break_before_caption") else "",
    E(ASOF_CAPTION),
    E(secs["exchange_rates"]["heading"]), secs["exchange_rates"]["caption"] % (E(mk["fx_base_date"]), E(mk["fx_prior_date"])), grid(fx_cells),
    "page-break-before" if secs["world_indices"].get("page_break_before") else "",
    E(secs["world_indices"]["heading"]), secs["world_indices"]["caption"] % E(mk.get("indices_asof_label") or mk.get("indices_asof") or "the latest completed session"), grid(idx_cells),
    "page-break-before" if secs["commodities"].get("page_break_before") else "",
    E(secs["commodities"]["heading"]), sourced_para(cm["summary"], cm.get("summary_sources")), grid(com_cells),
    "page-break-before" if secs["top_performers"].get("page_break_before") else "",
    E(secs["top_performers"]["heading"]), secs["top_performers"]["caption"], perf_earnings_html,
    E(secs["capital_raises"]["heading"]), secs["capital_raises"]["caption"], cr_html,
    E(secs["tech"]["heading"]), tech_html,
    E(secs["world_news"]["heading"]), news_html,
    E(secs["world_sport"]["heading"]), sport_html,
    E(br["name"]), E(br["company"]), E(br["site_url"]), E(br["site"]), GEN_NOTE, EDITION,
    E(rotation_note(cr, eg, HAD_PREVIOUS_EDITION)),
    E(cfg["footer"]["disclaimer"]),
    E(blocked_outlets_note(nb, cfg["footer"]["working_substitutes"]))
)

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
print("market-news words:", len(pc["market_news"]["paragraph"].split()))
print("rate cells:", len(fx_cells), "indices:", len(idx_cells), "commodities:", len(com_cells))
print("perf blocks:", len(seq), "outlets:", len(outlets), "sport codes:", len(sp["codes"]))
