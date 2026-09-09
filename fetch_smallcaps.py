#!/usr/bin/env python3
"""Authenticated SmallCaps.com.au scraper.

Logs in via Auth0/InvestHouse using credentials from .env.local, caches the
session cookies for up to 12 hours, and exposes parsers for:
- upcoming IPOs and new listings (/upcoming-ipos)
- live placements and entitlement offers (logged-in homepage)
- latest news articles (/latest-news), useful for earnings filtering elsewhere.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_PATH = DATA_DIR / ".smallcaps_session.json"
COOKIE_MAX_AGE_HOURS = 12


def _load_env():
    """Load .env.local into os.environ if it exists."""
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if key in os.environ:
            continue
        val = val.strip().strip('"').strip("'")
        os.environ[key] = val


def credentials():
    _load_env()
    return os.environ.get("SMALLCAPS_EMAIL"), os.environ.get("SMALLCAPS_PASSWORD")


def _cache_is_valid(email):
    if not CACHE_PATH.exists():
        return False
    try:
        data = json.loads(CACHE_PATH.read_text())
    except (ValueError, OSError):
        return False
    if data.get("email") != email:
        return False
    ts = data.get("ts")
    if not ts:
        return False
    try:
        cached = datetime.fromisoformat(ts)
    except ValueError:
        return False
    age = datetime.now() - cached
    return age < timedelta(hours=COOKIE_MAX_AGE_HOURS)


def _load_cached_cookies():
    try:
        data = json.loads(CACHE_PATH.read_text())
        return data.get("cookies", [])
    except (ValueError, OSError):
        return []


def _save_cached_cookies(email, cookies):
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(
            {"email": email, "ts": datetime.now().isoformat(), "cookies": cookies},
            indent=2,
            ensure_ascii=False,
        )
    )


def _requests_session(cookies):
    import requests

    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-AU,en;q=0.9",
        }
    )
    for c in cookies:
        s.cookies.set(
            c["name"],
            c["value"],
            domain=c.get("domain", ""),
            path=c.get("path", "/"),
        )
    return s


def _fetch_with_cookies(url, cookies, timeout=30):
    s = _requests_session(cookies)
    r = s.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def login(headless=True):
    """Perform Auth0 login and return cookie list, or None on failure."""
    email, pw = credentials()
    if not email or not pw:
        print("  ! SmallCaps credentials not found in .env.local", file=sys.stderr)
        return None

    if _cache_is_valid(email):
        return _load_cached_cookies()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            try:
                page.goto("https://smallcaps.com.au/", wait_until="networkidle")
                page.click("text=LOG IN")
                page.wait_for_url("https://auth.investhouse.ai/**")
                page.fill("input[name=username]", email)
                page.click("button[type=submit]")
                page.wait_for_timeout(2000)
                page.fill("input[type=password]:not(.hide)", pw)
                page.click("button[type=submit]")
                page.wait_for_timeout(5000)
                # Confirm we landed back on smallcaps with the portal visible.
                html_text = page.content()
                if "Investor Portal" not in html_text:
                    print(
                        "  ! SmallCaps login did not reach Investor Portal",
                        file=sys.stderr,
                    )
                    return None
                cookies = context.cookies()
                _save_cached_cookies(email, cookies)
                return cookies
            finally:
                browser.close()
    except PWTimeout as exc:
        print("  ! SmallCaps login timed out: %s" % exc, file=sys.stderr)
        return None
    except Exception as exc:
        print("  ! SmallCaps login failed: %s" % exc, file=sys.stderr)
        return None


def ensure_cookies():
    """Return valid cookies, refreshing the session if necessary."""
    email, _ = credentials()
    if email and _cache_is_valid(email):
        return _load_cached_cookies()
    return login()


def fetch_html(url):
    """Fetch a SmallCaps URL with the logged-in session via requests."""
    cookies = ensure_cookies()
    if not cookies:
        return None
    try:
        return _fetch_with_cookies(url, cookies)
    except Exception as exc:
        print("  ! SmallCaps fetch %s failed: %s" % (url, exc), file=sys.stderr)
        return None


def fetch_html_js(url, headless=True):
    """Fetch a SmallCaps URL with the logged-in session via Playwright.

    Some SmallCaps content (e.g. the logged-in Investor Portal placements)
    is rendered client-side, so a real browser is required.
    """
    email, pw = credentials()
    if not email or not pw:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            try:
                # Load cached cookies if valid.
                if _cache_is_valid(email):
                    context.add_cookies(_load_cached_cookies())
                    page.goto(url, wait_until="networkidle")
                else:
                    page.goto("https://smallcaps.com.au/", wait_until="networkidle")
                    page.click("text=LOG IN")
                    page.wait_for_url("https://auth.investhouse.ai/**")
                    page.fill("input[name=username]", email)
                    page.click("button[type=submit]")
                    page.wait_for_timeout(2000)
                    page.fill("input[type=password]:not(.hide)", pw)
                    page.click("button[type=submit]")
                    page.wait_for_timeout(5000)
                    _save_cached_cookies(email, context.cookies())
                    page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(3000)
                return page.content()
            finally:
                browser.close()
    except Exception as exc:
        print("  ! SmallCaps JS fetch %s failed: %s" % (url, exc), file=sys.stderr)
        return None


class _TableParser(HTMLParser):
    """Very small table parser using only the standard library."""

    def __init__(self):
        super().__init__()
        self.tables = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._in_a = False
        self._a_href = None
        self._cell_text = []
        self._current_row = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self._in_table = True
            self.tables.append([])
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_table and tag in ("td", "th"):
            self._in_cell = True
            self._cell_text = []
        elif self._in_cell and tag == "a" and "href" in attrs:
            self._in_a = True
            self._a_href = attrs["href"]

    def handle_endtag(self, tag):
        if tag == "table":
            self._in_table = False
        elif self._in_table and tag == "tr":
            self._in_row = False
            if self.tables:
                self.tables[-1].append(self._current_row)
            self._current_row = []
        elif self._in_table and tag in ("td", "th"):
            self._in_cell = False
            text = re.sub(r"\s+", " ", "".join(self._cell_text)).strip()
            if self._a_href:
                text = "%s [%s]" % (text, self._a_href) if text else self._a_href
                self._a_href = None
            self._current_row.append(text)
        elif tag == "a":
            self._in_a = False

    def handle_data(self, data):
        if self._in_cell:
            self._cell_text.append(data)


def _clean_text(s):
    return re.sub(r"\s+", " ", s).strip() if s else ""


def parse_ipos(html):
    """Parse the upcoming IPOs table into capital-raise candidates.

    Returns a list of dicts with headline, detail, url, outlet keys.
    """
    if not html:
        return []
    parser = _TableParser()
    parser.feed(html)
    items = []
    for table in parser.tables:
        if not table:
            continue
        header = table[0]
        if "Company" not in header or "Raise" not in header:
            continue
        for row in table[1:]:
            if len(row) < 6:
                continue
            company = _clean_text(row[0])
            sector = _clean_text(row[1])
            raise_amt = _clean_text(row[2])
            price = _clean_text(row[3])
            list_date = _clean_text(row[4])
            stage = _clean_text(row[5])
            # Extract prospectus URL if present in the last cell.
            prospectus = ""
            m = re.search(r"\[([^\]]+)\]", row[-1])
            if m:
                prospectus = m.group(1)
            if not company or not raise_amt:
                continue
            code = ""
            code_m = re.search(r"\b([A-Z]{2,5})\s*$", company)
            if code_m:
                code = code_m.group(1)
                company = company[: code_m.start()].strip()
            detail = (
                "Upcoming %s IPO raising %s at %s, expected to list %s (stage: %s)."
                % (sector, raise_amt, price, list_date, stage)
            )
            url = prospectus if prospectus else "https://smallcaps.com.au/upcoming-ipos"
            items.append(
                {
                    "headline": "%s (%s) — %s IPO" % (company, code, raise_amt) if code else "%s — %s IPO" % (company, raise_amt),
                    "detail": detail,
                    "url": url,
                    "outlet": "Small Caps",
                    "published": datetime.now().isoformat(),
                }
            )
    return items


def parse_placements(html):
    """Parse the logged-in homepage 'Live Placements' grid.

    Returns a list of dicts with headline, detail, url, outlet keys.
    """
    if not html:
        return []
    items = []
    idx = html.find("Live Placements")
    if idx == -1:
        return items
    chunk = html[idx : idx + 8000]
    rows = re.findall(
        r'grid-template-columns:\s*2fr[^"]*"[^>]*>(.*?)</div>\s*</div>',
        chunk,
        re.S,
    )
    for row in rows:
        cells = re.findall(r"<div[^>]*>([^<].*?)</div>", row, re.S)
        flat = [
            _clean_text(re.sub(r"<[^>]+>", " ", c))
            for c in cells
            if c.strip()
        ]
        # Drop the header row.
        if not flat or flat[0].lower() == "issuer":
            continue
        if len(flat) < 3:
            continue
        issuer = flat[0]
        offer_type = flat[1]
        raise_amt = flat[2]
        pct_match = re.search(r'<div[^>]*>(\d+%)</div>', row)
        subscription = pct_match.group(1) if pct_match else ""
        if not issuer or not raise_amt:
            continue
        detail = "%s %s raising %s" % (issuer, offer_type, raise_amt)
        if subscription:
            detail += "; subscription %s" % subscription
        items.append(
            {
                "headline": "%s — %s" % (issuer, raise_amt),
                "detail": detail,
                "url": "https://smallcaps.com.au/",
                "outlet": "Small Caps",
                "published": datetime.now().isoformat(),
            }
        )
    return items


def parse_latest_news(html, max_items=20):
    """Parse article cards from SmallCaps latest-news page.

    Returns a list of dicts with title, url, detail, published, outlet keys.
    """
    if not html:
        return []
    # The latest-news page renders article cards as <a class="group block"
    # href="/article/..."> with the headline inside <h3>.
    pattern = (
        r'<a[^>]*class="[^"]*group block[^"]*"[^>]*'
        r'href="(/article/[^"]+)"[^>]*>(.*?)</a>'
    )
    matches = re.findall(pattern, html, re.S)
    items = []
    for href, inner in matches[:max_items]:
        title_match = re.search(r"<h[23][^>]*>(.*?)</h[23]>", inner, re.S)
        title = (
            _clean_text(re.sub(r"<[^>]+>", " ", title_match.group(1)))
            if title_match
            else ""
        )
        if not title:
            continue
        detail_match = re.search(
            r'class="[^"]*line-clamp-[23][^"]*"[^>]*>(.*?)</', inner, re.S
        )
        detail = (
            _clean_text(re.sub(r"<[^>]+>", " ", detail_match.group(1)))
            if detail_match
            else title
        )
        items.append(
            {
                "title": title,
                "url": "https://smallcaps.com.au" + href,
                "detail": detail,
                "published": datetime.now().isoformat(),
                "outlet": "Small Caps",
            }
        )
    return items


def fetch_capraise_items():
    """Return SmallCaps IPO and live placement items for the ANZ region."""
    ipo_html = fetch_html("https://smallcaps.com.au/upcoming-ipos")
    home_html = fetch_html_js("https://smallcaps.com.au/")
    items = []
    items.extend(parse_ipos(ipo_html))
    items.extend(parse_placements(home_html))
    return items


def fetch_earnings_candidates():
    """Return latest SmallCaps news articles for downstream earnings filtering."""
    html = fetch_html("https://smallcaps.com.au/latest-news")
    return parse_latest_news(html)


if __name__ == "__main__":
    print("SmallCaps login test...")
    cookies = ensure_cookies()
    print("cookies:", len(cookies) if cookies else "None")
    if cookies:
        print("IPOs:", len(parse_ipos(fetch_html("https://smallcaps.com.au/upcoming-ipos"))))
        print("Placements:", len(parse_placements(fetch_html_js("https://smallcaps.com.au/"))))
        print("Latest news:", len(parse_latest_news(fetch_html("https://smallcaps.com.au/latest-news"))))
