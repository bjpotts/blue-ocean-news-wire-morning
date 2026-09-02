#!/usr/bin/env python3
"""Shared Google News RSS lookup for the Market Wrap Up fetchers.

Both the performers fetcher (why did this stock move?) and the commodities
fetcher (what drove the complex today?) need recent, dated, linkable press.
The logic lives here so the two cannot drift apart.

Yahoo Finance's search endpoint is not used: it rate-limits this environment
to 429 on both query hosts.
"""
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}

# Quote, chart and screener pages rank well for a company or commodity name but
# report nothing. Citing one as the reason something moved would be misleading,
# so they are rejected outright rather than used as a weak catalyst.
NOISE_TITLE = re.compile(
    r"(\u682a\u4fa1\u30c1\u30e3\u30fc\u30c8|\u63b2\u793a\u677f|\u6d41\u52a8\u6bd4\u7387"
    r"|\u884c\u60c5|\u5be6\u6642\u5831\u50f9"
    r"|stock price and chart|price and chart|chart-analyse|technische analyse"
    r"|aktienkurs|kursziel|chart\s*\||\bquote\b|cota\u00e7\u00f5es"
    r"|share price history|dividend history)", re.I)

NOISE_PUBLISHER = {"tradingview", "moomoo", "wallmine", "investing.com",
                   "marketscreener", "simply wall st", "stockinvest.us",
                   "yahoo!\u30d5\u30a1\u30a4\u30ca\u30f3\u30b9"}


def is_noise(item):
    """True when an item is a quote/chart page rather than reporting."""
    if NOISE_TITLE.search(item["title"]):
        return True
    return item["publisher"].strip().lower() in NOISE_PUBLISHER


def news_items(query, gl="US", ceid="US:en", timeout=30):
    """Recent press for a query, newest first. Returns [] rather than raising."""
    url = ("https://news.google.com/rss/search?q=%s&hl=en-%s&gl=%s&ceid=%s"
           % (urllib.parse.quote(query), gl, gl, ceid))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
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
