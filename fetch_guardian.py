#!/usr/bin/env python3
"""Fetch all five The Guardian editions via their RSS feeds and write data/guardian.json.

The Guardian publishes separate edition sites (International, UK, US, Australia,
Europe). Each has a working RSS feed (https://www.theguardian.com/{edition}/rss)
that is far more reliable than scraping the homepage. This script pulls the
latest stories per edition and writes them in the same outlet format used by
news-a.json / news-b.json so build.py can render them as World News sections.
"""
import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

EDITIONS = [
    {"key": "gint", "name": "The Guardian — International", "site": "theguardian.com/international",
     "rss": "https://www.theguardian.com/international/rss",
     "summary": "The Guardian's International edition round-up, blending the paper's global reporting on politics, climate and conflict with its in-depth features and analysis."},
    {"key": "guk", "name": "The Guardian — UK", "site": "theguardian.com/uk",
     "rss": "https://www.theguardian.com/uk/rss",
     "summary": "The Guardian's UK edition, covering British politics, the economy, public services and society from Westminster to the regions."},
    {"key": "gus", "name": "The Guardian — US", "site": "theguardian.com/us",
     "rss": "https://www.theguardian.com/us-news/rss",
     "summary": "The Guardian's US edition, reporting on the White House, Congress, the midterm campaign and American social and cultural stories."},
    {"key": "gau", "name": "The Guardian — Australia", "site": "theguardian.com/au",
     "rss": "https://www.theguardian.com/australia-news/rss",
     "summary": "The Guardian's Australian edition, covering federal politics, the economy, the environment and domestic news from an independent, progressive lens."},
    {"key": "geu", "name": "The Guardian — Europe", "site": "theguardian.com/europe",
     "rss": "https://www.theguardian.com/europe/rss",
     "summary": "The Guardian's Europe edition, tracking the EU, the war in Ukraine and political and economic developments across the continent."},
]

# Sections that are clearly not hard news for the digest's purposes (features,
# lifestyle, sport, culture, galleries, opinion). We drop these to keep the
# outlet list focused on genuine news, matching the tone of the other outlets.
SKIP_PATH = re.compile(
    r"/(sport|football|cricket|rugby-union|tennis|cycling|lifeandstyle|food|fashion|"
    r"culture|music|film|tv-and-radio|stage|books|artanddesign|games|"
    r"commentisfree|opinion|thefilter|environment/ng-interactive|"
    r"news/ng-interactive)/",
    re.I,
)


def fetch(url, tries=3):
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"}
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == tries - 1:
                print(f"  ! failed {url}: {e}", file=sys.stderr)
                return None
            time.sleep(2)
    return None


def parse_items(xml):
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        it = m.group(1)
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        l = re.search(r"<link>(https://www\.theguardian\.com/[^<]+)</link>", it)
        d = re.search(r"<dc:date>([^<]+)</dc:date>", it)
        if not (t and l):
            continue
        title = html.unescape(t.group(1)).strip()
        url = l.group(1)
        date = d.group(1) if d else None
        items.append({"title": title, "url": url, "date": date})
    return items


def fresh(items, max_days=2):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_days)
    out = []
    for it in items:
        try:
            dt = datetime.fromisoformat(it["date"].replace("Z", "+00:00"))
        except Exception:
            dt = None
        if dt and dt < cutoff:
            continue
        out.append(it)
    return out


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(base, "data", "guardian.json")
    os.makedirs(os.path.join(base, "data"), exist_ok=True)

    outlets = []
    used_urls = set()
    for ed in EDITIONS:
        xml = fetch(ed["rss"])
        if not xml:
            outlets.append({**ed, "note": "RSS fetch failed this run.", "items": []})
            continue
        items = [it for it in parse_items(xml) if not SKIP_PATH.search(it["url"])]
        items = fresh(items)
        # De-duplicate by URL across the feed (same story can appear multiple times)
        seen, dedup = set(), []
        for it in items:
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            dedup.append(it)
        # Drop stories already used by an earlier edition so each section is distinct
        fresh_items = [it for it in dedup if it["url"] not in used_urls]
        # Keep the top 6, drop pure "live blog" items that read as stream-of-consciousness
        picked = []
        for it in fresh_items[:12]:
            if re.search(r"/live/\d{4}/", it["url"]) and len(picked) >= 3:
                continue
            picked.append(it)
            if len(picked) >= 6:
                break
        items_out = []
        for it in picked:
            items_out.append({
                "headline": it["title"].split(" | ")[0].strip(),
                "detail": it["title"],
                "url": it["url"],
            })
            used_urls.add(it["url"])
        outlets.append({**ed, "note": None, "items": items_out})
        print(f"  {ed['key']} ({ed['name']}): {len(items_out)} items")

    with open(out_path, "w") as f:
        json.dump({"outlets": outlets}, f, indent=1, ensure_ascii=False)
    print(f"wrote {out_path}")
    return 0 if all(o["items"] for o in outlets) else 1


if __name__ == "__main__":
    sys.exit(main())
