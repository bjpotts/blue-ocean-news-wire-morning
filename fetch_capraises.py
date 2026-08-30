#!/usr/bin/env python3
"""Fetch Capital Raises & New Listings items for the Market Wrap Up digest.

Writes data/capraises.json. Each region pulls from business/markets feeds and
keeps only stories that genuinely read as equity capital markets activity -
placements, rights issues, secondary offerings, IPOs and new listings. A region
with nothing findable is reported honestly as empty rather than padded.
"""
import json
import os
import re
import sys

from feedlib import dedupe, fetch, parse_feed, provenance, recent, trim

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Words that mark a story as equity capital markets activity.
KEYWORDS = re.compile(
    r"\b(ipo|initial public offering|listing|lists on|relist|float(?:s|ed|ing)?|"
    r"placement|rights issue|entitlement offer|capital rais\w*|raises? \$|"
    r"raising|share (?:sale|offer|issue|placement)|secondary offering|"
    r"bookbuild|equity offering|share purchase plan|spp\b|debut(?:s|ed)?|"
    r"goes public|stock market debut|prospectus|underwrit\w+|"
    r"seeks? to raise|priced its|upsized)\b",
    re.I,
)

# Stories that merely mention a listed company but are not ECM activity.
EXCLUDE = re.compile(r"\b(listing agent|listings? of properties|real estate listing)\b", re.I)

REGIONS = [
    ("anz", "ANZ", 4, [
        ("Stockhead", "https://stockhead.com.au/feed/", r"stockhead\.com\.au"),
        ("Small Caps", "https://smallcaps.com.au/feed", r"smallcaps\.com\.au"),
    ]),
    ("asia", "Asia (Japan/Singapore/Hong Kong/China)", 4, [
        ("South China Morning Post", "https://www.scmp.com/rss/92/feed", r"scmp\.com"),
        ("South China Morning Post", "https://www.scmp.com/rss/91/feed", r"scmp\.com"),
    ]),
    ("us", "US", 4, [
        ("IPOScoop", "https://www.iposcoop.com/feed/", r"iposcoop\.com"),
        ("Nasdaq", "https://www.nasdaq.com/feed/rssoutbound?category=IPOs", r"nasdaq\.com"),
        ("CNBC Markets",
         "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
         r"cnbc\.com"),
    ]),
    ("uk", "UK", 3, [
        ("City A.M.", "https://www.cityam.com/category/markets/feed/", r"cityam\.com"),
        ("City A.M.", "https://www.cityam.com/feed/", r"cityam\.com"),
    ]),
    ("europe", "Europe", 3, [
        ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", r"bloomberg\.com"),
    ]),
    ("rest", "Rest (South America, Middle East, Africa, India etc)", 4, [
        ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss", r"bloomberg\.com"),
        ("CNBC Markets",
         "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
         r"cnbc\.com"),
    ]),
]

# Capital markets activity has a longer shelf life than a daily news headline,
# and every item carries its own dated source link, so the window here is wider
# than the three days used for the World News sections.
WINDOW_DAYS = 10


def summarise(name, items):
    if not items:
        return ("No capital raising or new listing activity could be verified from "
                "a linked source for %s this run, so nothing is listed rather than "
                "publishing an item without a working URL." % name)
    lead = items[0]["headline"]
    if len(items) == 1:
        return ("A single verifiable equity capital markets item was found for %s "
                "this run: %s" % (name, lead))
    return ("%s equity capital markets activity captured this run runs to %d items, "
            "led by %s. The remaining items cover the rest of the region's placement, "
            "offering and new listing flow as reported by the linked sources."
            % (name, len(items), lead))


def main():
    seen_urls, seen_titles = set(), set()
    regions = []
    empty = []

    for key, name, count, sources in REGIONS:
        picked = []
        for outlet, rss, filt in sources:
            if len(picked) >= count:
                break
            xml = fetch(rss)
            items = recent(parse_feed(xml, link_must_match=filt), max_days=WINDOW_DAYS)
            hits = [i for i in items
                    if KEYWORDS.search(i["title"] + " " + i["detail"])
                    and not EXCLUDE.search(i["title"])]
            for it in dedupe(hits, seen_urls, seen_titles):
                picked.append({
                    "headline": it["title"],
                    "detail": trim(it["detail"]) or it["title"],
                    "url": it["url"],
                    "outlet": outlet,
                    **provenance(it, rss),
                })
                if len(picked) >= count:
                    break

        print("  %-46s %d items" % (name, len(picked)))
        if not picked:
            empty.append(name)
        regions.append({"key": key, "name": name,
                        "summary": summarise(name, picked), "items": picked})

    with open(os.path.join(D, "capraises.json"), "w") as f:
        json.dump({"regions": regions}, f, indent=1, ensure_ascii=False)
    print("wrote capraises.json (%d regions)" % len(regions))
    if empty:
        print("NOTE: no verifiable items for: %s" % ", ".join(empty), file=sys.stderr)
    return 0 if len(regions) - len(empty) >= 3 else 1


if __name__ == "__main__":
    sys.exit(main())
