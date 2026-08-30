#!/usr/bin/env python3
"""Fetch fresh World News headlines for every outlet in the Market Wrap Up digest.

Writes data/news-a.json, data/news-b.json and data/news-abcus.json in the exact
schema build.py consumes. Each outlet is pulled from its published RSS feed,
which is far more reliable than scraping a homepage (several outlets silently
serve stale cached HTML to non-browser clients).
"""
import json
import os
import sys

from feedlib import fetch, parse_feed, parse_news_sitemap, recent, trim, dedupe

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# key, name, site, rss, how many items, optional URL filter, summary lead-in
OUTLETS_A = [
    ("abc", "ABC News Australia", "abc.net.au/news",
     "https://www.abc.net.au/news/feed/51120/rss.xml", 5, r"abc\.net\.au",
     "The ABC's Australian and international news file"),
    ("sbs", "SBS News Australia", "sbs.com.au/news",
     "https://www.sbs.com.au/news/topic/latest/feed", 5, r"sbs\.com\.au",
     "SBS News, covering Australian affairs with a strong multicultural and world focus"),
    ("rnz", "RNZ New Zealand", "rnz.co.nz",
     "https://www.rnz.co.nz/rss/national.xml", 5, r"rnz\.co\.nz",
     "Radio New Zealand's national news file"),
    ("scmp", "South China Morning Post", "scmp.com",
     "https://www.scmp.com/rss/91/feed", 5, r"scmp\.com",
     "The South China Morning Post, reporting from Hong Kong across Greater China and Asia"),
    ("cnn", "CNN", "cnn.com",
     "https://www.cnn.com/sitemap/news.xml", 5, r"cnn\.com/20\d\d/",
     "CNN's international edition"),
    ("fox", "Fox News", "foxnews.com",
     "https://moxie.foxnews.com/google-publisher/latest.xml", 5, r"foxnews\.com",
     "Fox News, covering US politics and national affairs"),
    ("wsj", "The Wall Street Journal", "wsj.com",
     "https://feeds.content.dowjones.io/public/rss/RSSWorldNews", 5, r"wsj\.com",
     "The Wall Street Journal's world news wire"),
]

OUTLETS_B = [
    ("time", "Time", "time.com",
     "https://time.com/feed/", 5, r"time\.com",
     "Time magazine, covering US and world affairs"),
    ("variety", "Variety", "variety.com",
     "https://variety.com/feed/", 5, r"variety\.com",
     "Variety, on the business of entertainment"),
    ("bloomberg", "Bloomberg", "bloomberg.com",
     "https://feeds.bloomberg.com/markets/news.rss", 5, r"bloomberg\.com",
     "Bloomberg's markets and business file"),
    ("bbc", "BBC", "bbc.com",
     "https://feeds.bbci.co.uk/news/world/rss.xml", 5, r"bbc\.(com|co\.uk)",
     "The BBC's world news service"),
    ("france24", "France 24", "france24.com",
     "https://www.france24.com/en/rss", 5, r"france24\.com",
     "France 24's English service, reporting from Paris on Europe, Africa and the Middle East"),
    ("aljazeera", "Al Jazeera", "aljazeera.com",
     "https://www.aljazeera.com/xml/rss/all.xml", 5, r"aljazeera\.com",
     "Al Jazeera English, with strong Middle East and Africa coverage"),
]

ABC_US = ("abcus", "ABC News (US)", "abcnews.go.com",
          "https://abcnews.go.com/abcnews/topstories", 5,
          r"abcnews\.(go\.)?com/[A-Za-z]+/",
          "ABC News in the United States, the network's national and world file")

NBC = ("nbc", "NBC News", "nbcnews.com",
       "https://feeds.nbcnews.com/nbcnews/public/news", 5, r"nbcnews\.com",
       "NBC News, covering US national news and politics")

THEHILL = ("thehill", "The Hill", "thehill.com",
           "https://thehill.com/news/feed/", 5, r"thehill\.com",
           "The Hill, reporting on Congress, the White House and US policy")

# NBC and The Hill sit with the US broadcast/politics outlets in set B.
OUTLETS_B = [NBC, THEHILL] + OUTLETS_B


def build_outlet(spec, seen_urls, seen_titles):
    key, name, site, rss, count, filt, lead = spec
    xml = fetch(rss)
    if not xml:
        return {"key": key, "name": name, "site": site,
                "summary": "%s could not be reached this run." % name,
                "note": "RSS fetch failed this run; no headlines are shown rather "
                        "than republishing stale ones.",
                "items": []}

    items = parse_news_sitemap(xml, link_must_match=filt) if "sitemap" in rss \
        else parse_feed(xml, link_must_match=filt)
    items = recent(items, max_days=3)
    # abcnews.com and abcnews.go.com are the same site; normalise on the
    # canonical news host so every link resolves to the news property.
    for it in items:
        it["url"] = it["url"].replace("//abcnews.com/", "//abcnews.go.com/")
    items = dedupe(items, seen_urls, seen_titles)[:count]

    out_items = []
    for it in items:
        detail = trim(it["detail"]) or it["title"]
        out_items.append({
            "headline": it["title"],
            "detail": detail,
            "url": it["url"],
        })

    if out_items:
        lead_words = "; ".join(i["headline"] for i in out_items[:3])
        summary = "%s is leading with %s." % (lead, lead_words)
    else:
        summary = "%s returned no fresh dated headlines this run." % name

    return {"key": key, "name": name, "site": site, "summary": summary,
            "note": None if out_items else "No dated items in the feed this run.",
            "items": out_items}


def main():
    seen_urls, seen_titles = set(), set()
    ok = True

    a = [build_outlet(s, seen_urls, seen_titles) for s in OUTLETS_A]
    abcus = build_outlet(ABC_US, seen_urls, seen_titles)
    b = [build_outlet(s, seen_urls, seen_titles) for s in OUTLETS_B]

    for group, label in ((a, "news-a"), (b, "news-b")):
        for o in group:
            print("  %-10s %-28s %d items" % (label, o["name"], len(o["items"])))
            if not o["items"]:
                ok = False
    print("  news-abcus %-28s %d items" % (abcus["name"], len(abcus["items"])))

    with open(os.path.join(D, "news-a.json"), "w") as f:
        json.dump({"outlets": a}, f, indent=1, ensure_ascii=False)
    with open(os.path.join(D, "news-b.json"), "w") as f:
        json.dump({"outlets": b, "blocked": []}, f, indent=1, ensure_ascii=False)
    with open(os.path.join(D, "news-abcus.json"), "w") as f:
        json.dump({"outlet": abcus}, f, indent=1, ensure_ascii=False)

    print("wrote news-a.json, news-b.json, news-abcus.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
