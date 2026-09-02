#!/usr/bin/env python3
"""Shared RSS/Atom helpers for the Market Wrap Up data fetchers."""
import html
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125 Safari/537.36")


def fetch(url, tries=3, timeout=30):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as exc:
            if i == tries - 1:
                print("  ! failed %s: %s" % (url, exc), file=sys.stderr)
                return None
            time.sleep(2)
    return None


def _tag(chunk, name):
    m = re.search(r"<%s[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</%s>" % (name, name),
                  chunk, re.S)
    return m.group(1).strip() if m else None


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
]

# Feeds quote named zones that strptime's %Z will not accept, so translate the
# ones actually seen across the outlets on this page into numeric offsets.
NAMED_ZONES = {
    "GMT": "+0000", "UTC": "+0000", "BST": "+0100",
    "CET": "+0100", "CEST": "+0200", "EST": "-0500", "EDT": "-0400",
    "CST": "-0600", "CDT": "-0500", "MST": "-0700", "MDT": "-0600",
    "PST": "-0800", "PDT": "-0700", "IST": "+0530", "JST": "+0900",
    "HKT": "+0800", "SGT": "+0800", "AEST": "+1000", "AEDT": "+1100",
    "NZST": "+1200", "NZDT": "+1300",
}


def _parse_date(raw):
    if not raw:
        return None
    raw = raw.strip()
    # Drop fractional seconds (CNN's sitemap emits 2026-08-30T16:01:57.933Z).
    raw = re.sub(r"(\d{2}:\d{2}:\d{2})\.\d+", r"\1", raw)
    raw = re.sub(r"\b([A-Z]{2,4})\s*$", lambda m: NAMED_ZONES.get(m.group(1), m.group(1)), raw)
    raw = re.sub(r"(\+\d{2}):(\d{2})$", r"\1\2", raw)
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def parse_feed(xml, link_must_match=None):
    """Parse RSS <item> or Atom <entry> blocks into dicts."""
    if not xml:
        return []
    items = []
    blocks = re.findall(r"<item[ >].*?</item>", xml, re.S)
    atom = not blocks
    if atom:
        blocks = re.findall(r"<entry[ >].*?</entry>", xml, re.S)

    for chunk in blocks:
        title = strip_html(_tag(chunk, "title"))
        if atom:
            # Single-quoted attributes are valid XML and some Atom feeds use
            # them; matching only double quotes silently emptied those feeds.
            lm = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', chunk)
            link = lm.group(1) if lm else None
        else:
            link = _tag(chunk, "link")
            if not link or not link.startswith("http"):
                lm = re.search(r"<link[^>]*>\s*(https?://[^\s<]+)", chunk)
                link = lm.group(1) if lm else link
        if not (title and link and link.startswith("http")):
            continue
        link = html.unescape(link).strip()
        if link_must_match and not re.search(link_must_match, link):
            continue
        detail = strip_html(_tag(chunk, "description") or _tag(chunk, "summary")
                            or _tag(chunk, "content:encoded") or "")
        raw_date = (_tag(chunk, "pubDate") or _tag(chunk, "dc:date")
                    or _tag(chunk, "published") or _tag(chunk, "updated"))
        items.append({
            "title": title,
            "url": link,
            "detail": detail,
            "date": _parse_date(raw_date),
        })
    return items


def parse_news_sitemap(xml, link_must_match=None):
    """Parse a Google-News-style sitemap (<url><loc>+<news:title>+date)."""
    if not xml:
        return []
    items = []
    for chunk in re.findall(r"<url>.*?</url>", xml, re.S):
        loc = _tag(chunk, "loc")
        title = strip_html(_tag(chunk, "news:title"))
        raw_date = _tag(chunk, "news:publication_date")
        if not (loc and title):
            continue
        loc = html.unescape(loc).strip()
        if link_must_match and not re.search(link_must_match, loc):
            continue
        items.append({"title": title, "url": loc, "detail": "",
                      "date": _parse_date(raw_date)})
    return items


def recent(items, max_days=3):
    """Keep items dated within max_days. Undated items are kept."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    return [i for i in items if i["date"] is None or i["date"] >= cutoff]


def trim(text, limit=240):
    """Cut a description to one clean sentence-ish string."""
    text = strip_html(text)
    if not text:
        return ""
    text = re.sub(r"\s*(Continue reading|Read more|The post .*)$", "", text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    dot = cut.rfind(". ")
    if dot > 60:
        return cut[:dot + 1]
    return cut.rsplit(" ", 1)[0] + "\u2026"


def dedupe(items, seen_urls, seen_titles):
    out = []
    for it in items:
        key = re.sub(r"[^a-z0-9]+", "", it["title"].lower())[:70]
        if it["url"] in seen_urls or key in seen_titles:
            continue
        seen_urls.add(it["url"])
        seen_titles.add(key)
        out.append(it)
    return out


def provenance(item, source_url):
    """Discovery record for a story, kept alongside it so a headline can be
    traced back later: the feed it was found in, the publication time the feed
    reported, and when this run pulled it.

    Fetchers differ in how they carry the item date -- parse_feed yields a
    datetime, while the Guardian fetcher keeps the raw <dc:date> string -- so
    normalise both to an ISO string here."""
    published = item.get("date")
    if isinstance(published, str):
        parsed = _parse_date(published)
        # Drop anything that will not parse rather than passing a raw string
        # through to a timestamp column downstream.
        published = parsed.isoformat() if parsed else None
    elif published is not None:
        published = published.isoformat()
    return {
        "source_url": source_url,
        "published": published,
        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
