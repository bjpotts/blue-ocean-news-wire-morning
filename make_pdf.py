#!/usr/bin/env python3
"""Render the full Market Wrap Up digest to a styled multi-page PDF."""
import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT / "preview.html"


def edition_suffix():
    """Return 'am' for roughly 04:00-16:00 Sydney time, else 'pm'."""
    # build.py writes the edition into preview.html; fall back to current UTC.
    if PREVIEW.exists():
        text = PREVIEW.read_text()
        m = re.search(r'<span class="edition-chip">([^<]+)</span>', text)
        if m:
            return "am" if "morning" in m.group(1).lower() else "pm"
    hour = datetime.utcnow().hour
    # Sydney is UTC+10 (ignoring DST for a rough guess)
    sydney_hour = (hour + 10) % 24
    return "am" if 4 <= sydney_hour < 16 else "pm"


def edition_date():
    """The edition date as printed in the masthead dateline, so the page
    footer matches the report rather than the print job's own clock."""
    if PREVIEW.exists():
        m = re.search(
            r"(\w+day \d{1,2} \w+ \d{4})", PREVIEW.read_text())
        if m:
            return m.group(1)
    return datetime.now().strftime("%A %d %B %Y")


def footer_template():
    """Per-page footer: Blue Ocean Equities left, page number centred, the
    edition date right, under a cerulean rule matching the page palette."""
    return (
        '<div style="width:100%;font-size:10px;font-family:\'IBM Plex Mono\','
        'ui-monospace,Menlo,monospace;color:#5b7078;padding:0 12mm;'
        '-webkit-print-color-adjust:exact;">'
        '<div style="border-top:1px solid #00A0D2;padding-top:4px;'
        'display:flex;align-items:center;">'
        '<span style="flex:1;text-align:left;">Blue Ocean Equities</span>'
        '<span style="flex:1;text-align:center;">'
        '<span class="pageNumber"></span></span>'
        '<span style="flex:1;text-align:right;">' + edition_date() + "</span>"
        "</div></div>"
    )


def output_path():
    date_str = datetime.now().strftime("%Y-%m-%d")
    return ROOT / f"market-wrap-up-{date_str}-{edition_suffix()}.pdf"


async def render_pdf():
    if not PREVIEW.exists():
        print(f"preview.html not found at {PREVIEW}", file=sys.stderr)
        sys.exit(1)

    out = output_path()
    url = PREVIEW.as_uri()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        # Wait for fonts and any async weather script.
        await page.wait_for_timeout(2000)
        await page.pdf(
            path=str(out),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=footer_template(),
            margin={"top": "12mm", "right": "12mm", "bottom": "18mm", "left": "12mm"},
        )
        await browser.close()

    size_kb = out.stat().st_size / 1024
    print(f"pdf: {out}")
    print(f"pdf bytes: {out.stat().st_size} ({size_kb:.1f} KB)")
    return out


if __name__ == "__main__":
    asyncio.run(render_pdf())
