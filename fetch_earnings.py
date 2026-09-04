#!/usr/bin/env python3
"""Fetch Market Earnings Reporting items for the Market Wrap Up digest.

Writes data/earnings.json. Each region pulls from business/markets feeds and
keeps only stories that genuinely read as corporate earnings activity -
quarterly/half-year/full-year results, profit or loss reports, guidance
updates and earnings calendar previews. A region with nothing findable is
reported honestly as empty rather than padded.
"""
import json
import os
import re
import sys

from feedlib import dedupe, fetch, parse_feed, provenance, recent, trim

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Words that mark a story as corporate earnings/results activity. Deliberately
# specific rather than single generic words like "guidance"/"dividend"/"Q4" -
# those fire on unrelated exploration-update and capital-raise stories that
# happen to mention a quarter or an EPS figure in passing.
KEYWORDS = re.compile(
    r"\b(earnings (?:call|report|season|beat|miss|per share)|"
    r"quarterly results|half-year results|full-year results|"
    r"interim results|annual results|"
    r"(?:quarterly|half-year|full-year|interim|annual) (?:profit|loss|revenue|earnings)|"
    r"reports? (?:a |its )?(?:quarterly|half-year|full-year|interim|annual) "
    r"(?:profit|loss|revenue|results)|"
    r"profit (?:rises?|falls?|jumps?|slumps?|beats?|misses?|before tax)|"
    r"(?:profit|revenue|loss) (?:surge|soar|plunge|tumble|slump|jump)s?|"
    r"net profit|net loss|earnings guidance|profit guidance|"
    r"results season|reporting season|"
    r"first[- ]half (?:profit|loss|results|earnings)|"
    r"second[- ]half (?:profit|loss|results|earnings)|"
    r"(?:first|second|third|fourth)[- ]quarter (?:profit|loss|results|earnings)|"
    r"q[1-4] (?:profit|loss|results|earnings)|"
    r"beats? (?:earnings |profit )?(?:estimates|expectations|forecasts)|"
    r"misses? (?:earnings |profit )?(?:estimates|expectations|forecasts)|"
    r"posts? (?:a |its )?(?:quarterly|half-year|full-year|interim|annual)? ?"
    r"(?:profit|loss|revenue)|dividend (?:cut|rise|increase|reduced|steady|"
    r"boosted|slashed|maintained))\b",
    re.I,
)

# Stories that merely mention "earnings"/"results" but are not corporate
# reporting activity (e.g. sports results, election results, exam results).
EXCLUDE = re.compile(
    r"\b(election results?|match results?|exam results?|test results?|"
    r"search results?|poll results?|survey results?|drilling results?|"
    r"assay results?|trial results?|study results?)\b", re.I)

REGIONS = [
    ("anz", "ANZ", 5, [
        ("Stockhead", "https://stockhead.com.au/feed/", r"stockhead\.com\.au"),
        ("Small Caps", "https://smallcaps.com.au/feed", r"smallcaps\.com\.au"),
        ("The Market Herald", "https://themarketherald.com.au/feed/",
         r"themarket(?:herald|online)\.com\.au"),
    ]),
    ("asia", "Asia (Japan/Singapore/Hong Kong/China)", 5, [
        ("South China Morning Post", "https://www.scmp.com/rss/92/feed", r"scmp\.com"),
        ("South China Morning Post", "https://www.scmp.com/rss/91/feed", r"scmp\.com"),
    ]),
    ("us", "US", 5, [
        ("Nasdaq", "https://www.nasdaq.com/feed/rssoutbound?category=Earnings", r"nasdaq\.com"),
        ("CNBC Markets",
         "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
         r"cnbc\.com"),
    ]),
    ("uk", "UK", 5, [
        ("City A.M.", "https://www.cityam.com/category/earnings/feed/", r"cityam\.com"),
        ("City A.M.", "https://www.cityam.com/category/markets/feed/", r"cityam\.com"),
    ]),
    ("europe", "Europe", 5, [
        ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", r"bloomberg\.com"),
        ("Investing.com", "https://www.investing.com/rss/news_25.rss", r"investing\.com"),
    ]),
    ("rest", "Rest (South America, Middle East, Africa, India etc)", 5, [
        ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", r"bloomberg\.com"),
        ("CNBC Markets",
         "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
         r"cnbc\.com"),
        ("Investing.com", "https://www.investing.com/rss/news_25.rss", r"investing\.com"),
    ]),
]

# Earnings coverage moves fast around results day but calendar previews and
# call-highlight writeups stay relevant for a few days either side, so this
# window matches Capital Raises rather than the tighter World News window.
WINDOW_DAYS = 10


def summarise(name, items, fresh_count=None):
    if not items:
        return "No Company earnings reports available."
    lead = items[0]["headline"]
    # No fresh linked source turned up anything past what the last edition
    # already carried - say so plainly rather than implying new activity.
    stale_note = (" No newer earnings item has been reported for %s since the "
                  "last edition, so the same verified item(s) are carried "
                  "forward." % name) if fresh_count == 0 else ""
    if len(items) == 1:
        return ("A single verifiable earnings item was found for %s this run: "
                "%s.%s" % (name, lead, stale_note))
    return ("%s earnings reporting activity captured this run runs to %d items, "
            "led by %s. The remaining items cover the rest of the region's "
            "results, guidance and reporting-season flow as reported by the "
            "linked sources.%s" % (name, len(items), lead, stale_note))


def _load_prev_urls(path):
    """URLs shown per region in the last run, so a region doesn't keep
    resurfacing the same headline once a fresher match becomes available."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            prev = json.load(f)
    except (ValueError, OSError):
        return {}
    return {r["key"]: {it["url"] for it in r.get("items", [])}
            for r in prev.get("regions", [])}


def main():
    seen_urls, seen_titles = set(), set()
    regions = []
    empty = []
    prev_urls = _load_prev_urls(os.path.join(D, "earnings.json"))

    for key, name, count, sources in REGIONS:
        candidates = []
        for outlet, rss, filt in sources:
            xml = fetch(rss)
            items = recent(parse_feed(xml, link_must_match=filt), max_days=WINDOW_DAYS)
            hits = [i for i in items
                    if KEYWORDS.search(i["title"] + " " + i["detail"])
                    and not EXCLUDE.search(i["title"])]
            for it in dedupe(hits, seen_urls, seen_titles):
                candidates.append({
                    "headline": it["title"],
                    "detail": trim(it["detail"]) or it["title"],
                    "url": it["url"],
                    "outlet": outlet,
                    **provenance(it, rss),
                })

        # Prefer anything not shown last run; only fall back to a repeat
        # headline if there simply aren't enough fresh matches to fill count.
        prior = prev_urls.get(key, set())
        fresh = [c for c in candidates if c["url"] not in prior]
        repeat = [c for c in candidates if c["url"] in prior]
        picked = (fresh + repeat)[:count]

        print("  %-46s %d items (%d fresh, %d repeated from last run)"
              % (name, len(picked), min(len(fresh), len(picked)),
                 max(0, len(picked) - len(fresh))))
        if not picked:
            empty.append(name)
        regions.append({"key": key, "name": name,
                        "summary": summarise(name, picked, min(len(fresh), len(picked))),
                        "items": picked})

    with open(os.path.join(D, "earnings.json"), "w") as f:
        json.dump({"regions": regions}, f, indent=1, ensure_ascii=False)
    print("wrote earnings.json (%d regions)" % len(regions))
    if empty:
        print("NOTE: no verifiable items for: %s" % ", ".join(empty), file=sys.stderr)
    return 0 if len(regions) - len(empty) >= 3 else 1


if __name__ == "__main__":
    sys.exit(main())
