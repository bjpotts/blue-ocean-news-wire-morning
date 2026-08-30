#!/usr/bin/env python3
"""Fetch the top global technology stories for the Market Wrap Up digest.

Writes data/tech.json. Sources are deliberately spread across US, European,
Asian and Australian outlets so the section is genuinely global rather than
US-only.
"""
import json
import os
import sys

from feedlib import fetch, parse_feed, recent, trim, dedupe

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# outlet label, region label, rss, url filter, max items to take from this feed
SOURCES = [
    ("TechCrunch", "US", "https://techcrunch.com/feed/", r"techcrunch\.com", 2),
    ("The Verge", "US", "https://www.theverge.com/rss/index.xml", r"theverge\.com", 2),
    ("CNBC Technology", "US",
     "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910",
     r"cnbc\.com", 2),
    ("Ars Technica", "US", "https://feeds.arstechnica.com/arstechnica/index",
     r"arstechnica\.com", 1),
    ("BBC Technology", "Europe", "https://feeds.bbci.co.uk/news/technology/rss.xml",
     r"bbc\.(com|co\.uk)", 2),
    ("South China Morning Post", "Asia", "https://www.scmp.com/rss/36/feed",
     r"scmp\.com", 2),
    ("iTnews", "Australia", "https://www.itnews.com.au/RSS/rss.ashx",
     r"itnews\.com\.au", 2),
]

TARGET = 10


def main():
    seen_urls, seen_titles = set(), set()
    picked = []

    for outlet, region, rss, filt, take in SOURCES:
        xml = fetch(rss)
        items = recent(parse_feed(xml, link_must_match=filt), max_days=3)
        items = dedupe(items, seen_urls, seen_titles)[:take]
        for it in items:
            picked.append({
                "headline": it["title"],
                "detail": trim(it["detail"]) or it["title"],
                "outlet": outlet,
                "url": it["url"],
                "region": region,
            })
        print("  %-26s %-9s %d items" % (outlet, region, len(items)))

    # Top up to ten from the broadest feeds if any source came back thin.
    if len(picked) < TARGET:
        for outlet, region, rss, filt, _ in SOURCES:
            if len(picked) >= TARGET:
                break
            xml = fetch(rss)
            items = recent(parse_feed(xml, link_must_match=filt), max_days=3)
            for it in dedupe(items, seen_urls, seen_titles):
                picked.append({
                    "headline": it["title"],
                    "detail": trim(it["detail"]) or it["title"],
                    "outlet": outlet,
                    "url": it["url"],
                    "region": region,
                })
                if len(picked) >= TARGET:
                    break

    picked = picked[:TARGET]
    with open(os.path.join(D, "tech.json"), "w") as f:
        json.dump({"items": picked}, f, indent=1, ensure_ascii=False)
    print("wrote tech.json (%d stories)" % len(picked))
    return 0 if len(picked) >= 6 else 1


if __name__ == "__main__":
    sys.exit(main())
