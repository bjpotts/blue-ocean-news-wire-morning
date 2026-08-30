#!/usr/bin/env python3
"""Fetch World Sport headlines for the Market Wrap Up digest.

Writes data/sport.json. Each code is pulled from a published feed with real
dated article URLs; a code that returns nothing fresh is dropped from the
section rather than padded with stale items.
"""
import json
import os
import sys

from feedlib import fetch, parse_feed, recent, trim, dedupe

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# key, section name, item count, [(outlet label, rss, url filter), ...]
CODES = [
    ("nrl", "Rugby League (NRL) - Australia", 3, [
        ("Zero Tackle", "https://www.zerotackle.com/feed/", r"zerotackle\.com"),
    ]),
    ("afl", "AFL - Australia", 3, [
        ("AFL.com.au", "https://www.afl.com.au/rss", r"afl\.com\.au"),
    ]),
    ("rugby-union", "Rugby Union - Australia", 3, [
        ("Sky Sports Rugby Union", "https://www.skysports.com/rss/12321", r"skysports\.com"),
        ("Rugby World", "https://www.rugbyworld.com/feed", r"rugbyworld\.com"),
    ]),
    ("golf", "World Golf", 6, [
        ("Sky Sports Golf", "https://www.skysports.com/rss/12176", r"skysports\.com"),
        ("Yahoo Sports Golf", "https://sports.yahoo.com/golf/rss.xml", r"yahoo\.com"),
    ]),
    ("cricket", "Cricket - Worldwide", 3, [
        ("ESPNcricinfo", "https://www.espncricinfo.com/rss/content/story/feeds/0.xml",
         r"espncricinfo\.com"),
        ("Sky Sports Cricket", "https://www.skysports.com/rss/12123", r"skysports\.com"),
    ]),
    ("nfl", "NFL - US", 3, [
        ("Yahoo Sports", "https://sports.yahoo.com/nfl/rss.xml", r"yahoo\.com"),
    ]),
    ("nba", "NBA - US", 3, [
        ("Yahoo Sports", "https://sports.yahoo.com/nba/rss.xml", r"yahoo\.com"),
    ]),
    ("mlb", "MLB - US", 3, [
        ("Yahoo Sports", "https://sports.yahoo.com/mlb/rss.xml", r"yahoo\.com"),
    ]),
    ("f1", "Formula 1 - Europe", 3, [
        ("Sky Sports F1", "https://www.skysports.com/rss/12433", r"skysports\.com"),
        ("Formula1.com", "https://www.formula1.com/content/fom-website/en/latest/all.xml",
         r"formula1\.com"),
    ]),
    ("tennis", "Tennis - Rest of World", 3, [
        ("Yahoo Sports Tennis", "https://sports.yahoo.com/tennis/rss.xml", r"yahoo\.com"),
    ]),
]


def main():
    seen_urls, seen_titles = set(), set()
    codes = []
    thin = []

    for key, name, count, sources in CODES:
        items_out = []
        for outlet, rss, filt in sources:
            if len(items_out) >= count:
                break
            xml = fetch(rss)
            items = recent(parse_feed(xml, link_must_match=filt), max_days=3)
            for it in dedupe(items, seen_urls, seen_titles):
                items_out.append({
                    "headline": it["title"],
                    "detail": trim(it["detail"]) or it["title"],
                    "url": it["url"],
                    "outlet": outlet,
                })
                if len(items_out) >= count:
                    break

        print("  %-28s %d items" % (name, len(items_out)))
        if not items_out:
            thin.append(name)
            continue
        codes.append({"key": key, "name": name, "items": items_out})

    with open(os.path.join(D, "sport.json"), "w") as f:
        json.dump({"codes": codes}, f, indent=1, ensure_ascii=False)
    print("wrote sport.json (%d codes)" % len(codes))
    if thin:
        print("NOTE: dropped codes with no fresh dated items: %s"
              % ", ".join(thin), file=sys.stderr)
    return 0 if len(codes) >= 6 else 1


if __name__ == "__main__":
    sys.exit(main())
