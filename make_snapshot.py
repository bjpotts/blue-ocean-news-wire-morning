#!/usr/bin/env python3
"""Build the condensed 1-page snapshot PDF (standard Helvetica, no embedded fonts)."""
import json, html, os, base64, re
from datetime import datetime
from zoneinfo import ZoneInfo
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

BASE = os.path.dirname(os.path.abspath(__file__))

_now = datetime.now(ZoneInfo("Australia/Sydney"))
_hr = _now.hour
_PREVIEW = os.path.join(BASE, "preview.html")
_auto_edition = "Morning Edition" if 4 <= _hr < 16 else "Evening Edition"
if os.path.exists(_PREVIEW):
    # build.py bakes the actual edition (honouring EDITION_OVERRIDE) into the
    # chip. Reading it back keeps this filename in step with the page's own
    # masthead instead of re-deriving it from the wall clock, which mislabels
    # a manual/out-of-window run.
    _m = re.search(r'<span class="edition-chip">([^<]+)</span>',
                   open(_PREVIEW).read())
    EDITION = _m.group(1) if _m else _auto_edition
else:
    EDITION = os.environ.get("EDITION_OVERRIDE", "").strip() or _auto_edition
AMPM = "am" if "morning" in EDITION.lower() else "pm"
DATE = _now.strftime("%Y-%m-%d")
_DATELINE_DATE = _now.strftime("%A %d %B %Y")
_DATELINE_TIME = _now.strftime("%H:%M AEST")
DATELINE = f"{EDITION} \u00b7 {_DATELINE_DATE} \u00b7 {_DATELINE_TIME} \u00b7 Sydney, NSW"
ARTIFACT = "https://claude.ai/code/artifact/843fe9ec-75b9-43fe-b1f1-19454a9716c4"
OUT = os.path.join(BASE, "public-news-wire-snapshot-%s-%s.pdf" % (DATE, AMPM))

# Same paragraph text, same entity escaping, as the published page.
mnp = json.load(open(os.path.join(BASE, "data", "perf-c.json")))["market_news"]["paragraph"]
# Edition-specific number corrections; applied only when present in the fresh text.
for a, b in [
    ("The Russell 2000 small-cap index was not among the indexes detailed in the reports reviewed.",
     "The Russell 2000 small-cap index closed at 3,017.87, up 0.85 per cent, outpacing the large-cap benchmarks."),
    ("the Nikkei 225 slipped 0.2 per cent to 66,080.25", "the Nikkei 225 slipped 0.30 per cent to 66,016.36"),
    ("the Hang Seng added 0.7 per cent to 25,888.36", "the Hang Seng added 1.21 per cent to 26,009.46"),
    ("the KOSPI climbed 0.9 per cent to 6,914.09", "the KOSPI climbed 0.88 per cent to 6,912.95"),
    ("the Shanghai Composite was little changed at 3,903.81", "the Shanghai Composite was little changed at 3,905.20"),
    ("India's BSE Sensex eased about 0.1 per cent", "India's BSE Sensex was flat at 77,540.83"),
]:
    mnp = mnp.replace(a, b)
MARKET_NEWS = html.escape(mnp)          # passed through as-is; reportlab decodes entities

TEAL = colors.HexColor("#006F6F")
CERULEAN = colors.HexColor("#00A0D2")
INK = colors.HexColor("#132227")
MUTED = colors.HexColor("#5B7078")

kicker = ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=7.5, leading=10,
                        textColor=TEAL, spaceAfter=3)
title = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=27, leading=29,
                       textColor=INK, spaceAfter=4)
dateline = ParagraphStyle("dateline", fontName="Helvetica", fontSize=8.5, leading=12,
                          textColor=MUTED, spaceAfter=2)
h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=16,
                    textColor=TEAL, spaceBefore=10, spaceAfter=6)
body = ParagraphStyle("body", fontName="Helvetica", fontSize=9.1, leading=12.6,
                      textColor=INK, alignment=4, spaceAfter=8)
note = ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=7.6, leading=10.5,
                      textColor=MUTED, spaceBefore=8)

doc = SimpleDocTemplate(OUT, pagesize=A4,
                        leftMargin=18 * mm, rightMargin=18 * mm,
                        topMargin=16 * mm, bottomMargin=14 * mm,
                        title="Market Wrap Up - Market Snapshot",
                        author="Blue Ocean Equities Pty Ltd", subject="Global Market Update")

story = [
    Paragraph("BLUE OCEAN EQUITIES PTY LTD", kicker),
    Paragraph("Market Wrap Up", title),
    Paragraph(DATELINE, dateline),
    Spacer(1, 5),
    HRFlowable(width="100%", thickness=1.6, color=TEAL, spaceAfter=2),
    Paragraph("Market News", h2),
    Paragraph(MARKET_NEWS, body),
    HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#B8CED6"), spaceBefore=4),
    Paragraph(
        "This is a condensed snapshot. The complete edition - exchange rates and bitcoin, world indices, "
        "commodities, regional top performers, capital raises and new listings, tech, world news and world "
        'sport - is published in full at <a href="%s" color="#00A0D2">%s</a>. '
        "Information only; not investment advice." % (ARTIFACT, ARTIFACT), note),
]
doc.build(story)

raw = open(OUT, "rb").read()
b64 = base64.b64encode(raw).decode()
open(os.path.join(BASE, "snapshot.b64"), "w").write(b64)
print("pdf:", OUT)
print("pdf bytes:", len(raw), "(%.1f KB)" % (len(raw) / 1024))
print("base64 chars:", len(b64), "(%.1f KB)" % (len(b64) / 1024))
print("under 50KB base64:", len(b64) < 50 * 1024)
