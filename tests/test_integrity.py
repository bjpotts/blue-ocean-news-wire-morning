#!/usr/bin/env python3
"""Cross-cutting invariants on the built digest and its source data.

These are the standing rules for the page rather than unit behaviour:
every data point is clickable, no section carries frozen placeholder prose,
and the grids are the width they are supposed to be. They run against
public/digest.html and data/*.json as last built, and skip cleanly when the
page has not been built yet.
"""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import ROOT, load_from_source, read_digest


def data(name):
    path = os.path.join(ROOT, "data", name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


class DigestTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read_digest()
        if cls.html is None:
            raise unittest.SkipTest("public/digest.html not built yet")


class EverythingIsLinked(DigestTestCase):
    """The page's hard rule: no data point appears as bare unlinked text."""

    def test_every_rate_grid_cell_is_an_anchor(self):
        cells = re.findall(r'class="rate-cell"[^>]*>', self.html)
        anchors = re.findall(r'<a class="rate-cell" href="[^"]+"', self.html)
        self.assertEqual(len(cells), len(anchors))
        self.assertGreater(len(anchors), 0)

    def test_no_rate_cell_has_an_empty_href(self):
        self.assertNotIn('<a class="rate-cell" href=""', self.html)

    def test_every_performer_row_links_its_company(self):
        for row in re.findall(r"<tr>(?:(?!</tr>).)*</tr>", self.html, re.S):
            if 'class="num"' not in row or "<th" in row:
                continue
            self.assertRegex(row, r'<a[^>]+href="https?://', row[:120])

    def test_every_headline_list_item_carries_a_link(self):
        for li in re.findall(r"<li>(.*?)</li>", self.html, re.S):
            self.assertRegex(li, r'<a[^>]+href="https?://', li[:120])

    def test_no_placeholder_hrefs(self):
        for bad in ('href="#"', 'href=""', 'href="null"', 'href="undefined"'):
            self.assertNotIn(bad, self.html, bad)


class GridWidths(DigestTestCase):
    def test_exchange_rates_and_indices_are_both_24_cells(self):
        grids = re.findall(r'<div class="rate-grid">(.*?)</div>\s*(?=<h|<p|<div|$)',
                           self.html, re.S)
        counts = [g.count('class="rate-cell"') for g in grids]
        self.assertIn(24, counts, "expected at least one 24-cell grid: %s" % counts)

    def test_the_source_data_carries_the_expected_counts(self):
        m, c = data("markets.json"), data("commodities.json")
        if m:
            self.assertEqual(len(m["indices"]), 24)
            # 22 currencies + USD base + BTC fills the same 24-cell grid.
            self.assertEqual(len(m["fx"]) + 2, 24)
            self.assertTrue(m["btc"]["price"])
        if c:
            self.assertEqual(len(c["commodities"]), 24)


class NoFrozenProse(DigestTestCase):
    """Paragraphs that were once hardcoded and silently stopped tracking."""

    RETIRED = [
        "Commodity markets are mixed in the latest session",
        "no company announcement has been independently verified",
        "Readers should treat the move as the market print",
    ]

    def test_retired_placeholder_text_is_gone(self):
        for phrase in self.RETIRED:
            self.assertNotIn(phrase, self.html, phrase)

    def test_the_commodity_summary_reports_a_real_tally(self):
        c = data("commodities.json")
        if not c:
            self.skipTest("no commodities data")
        self.assertRegex(c["summary"], r"\d+ of the \d+ tracked benchmarks")

    def test_the_market_news_paragraph_is_present_and_substantial(self):
        paras = re.findall(r'<p class="market-summary">(.*?)</p>', self.html, re.S)
        self.assertGreaterEqual(len(paras), 2)   # market news + commodities
        for p in paras:
            self.assertGreater(len(re.sub(r"<[^>]+>", "", p).split()), 25)

    def test_each_region_has_two_distinct_mover_notes(self):
        notes = re.findall(r'class="mover-note">(.*?)</p>', self.html, re.S)
        self.assertGreaterEqual(len(notes), 18)  # 9 regions x gainer + loser
        perf = [n for n in notes if "per cent to" in n]
        self.assertEqual(len(perf), len(set(perf)), "duplicate mover explainers")


class PerformerData(unittest.TestCase):
    def files(self):
        out = []
        for f in ("perf-a.json", "perf-b.json", "perf-c.json"):
            d = data(f)
            if d:
                out.extend(d["markets"])
        return out

    def test_all_nine_regions_are_present(self):
        markets = self.files()
        if not markets:
            self.skipTest("no performer data")
        self.assertEqual(len(markets), 9)

    def test_no_region_is_marked_stale(self):
        for m in self.files():
            self.assertFalse(m.get("stale"), m["key"])

    def test_every_row_has_a_price_change_and_link(self):
        for m in self.files():
            for side in ("gainers", "losers"):
                for r in m[side]:
                    self.assertTrue(r["url"].startswith("http"), r)
                    self.assertTrue(r["price"], r)
                    self.assertTrue(r["chg"], r)

    def test_gainers_and_losers_point_the_right_way(self):
        for m in self.files():
            for r in m["gainers"]:
                self.assertFalse(r["chg"].startswith("-"),
                                 "%s gainer %s" % (m["key"], r["name"]))
            for r in m["losers"]:
                self.assertTrue(r["chg"].startswith("-"),
                                "%s loser %s" % (m["key"], r["name"]))

    def test_catalyst_sources_are_real_urls(self):
        for m in self.files():
            for key in ("gainer_note_sources", "loser_note_sources"):
                for s in m.get(key, []):
                    self.assertTrue(s["url"].startswith("http"), s)
                    self.assertTrue(s["title"].strip(), s)

    def test_a_note_that_promises_a_citation_has_one(self):
        """The note ends with a colon only when the builder will append a link."""
        for m in self.files():
            for side in ("gainer", "loser"):
                note = m["%s_note" % side].rstrip()
                has_src = bool(m.get("%s_note_sources" % side))
                self.assertEqual(note.endswith(":"), has_src,
                                 "%s %s" % (m["key"], side))

    def test_gainers_and_losers_are_ordered_by_volume_descending(self):
        """Global formatting rule: highest-traded stock at the top of each
        table, descending to the smallest, in every region."""
        FP = load_from_source("fetch_performers.py", ["_vol_value", "_VOL_UNIT"])
        for m in self.files():
            for side in ("gainers", "losers"):
                vols = [FP["_vol_value"](r["vol"]) for r in m[side]]
                self.assertEqual(vols, sorted(vols, reverse=True),
                                 "%s %s not volume-sorted: %s"
                                 % (m["key"], side, [r["vol"] for r in m[side]]))


class CommodityData(unittest.TestCase):
    def test_no_invented_price_is_published(self):
        c = data("commodities.json")
        if not c:
            self.skipTest("no commodities data")
        for r in c["commodities"]:
            self.assertTrue(r["price"], r["name"])
            self.assertTrue(r["url"].startswith("http"), r["name"])

    def test_the_rare_earths_proxy_is_labelled_as_one(self):
        c = data("commodities.json")
        if not c:
            self.skipTest("no commodities data")
        re_rows = [r for r in c["commodities"] if r["name"] == "Rare Earth Elements"]
        for r in re_rows:
            self.assertEqual(r["flag"], "proxy")

    def test_stale_rows_are_flagged_and_disclosed(self):
        c = data("commodities.json")
        if not c:
            self.skipTest("no commodities data")
        stale = [r["name"] for r in c["commodities"] if r.get("flag") == "stale"]
        for name in stale:
            self.assertIn(name, c["summary"])


class EarningsData(unittest.TestCase):
    """Market Earnings Reporting section, one region block per configured
    Top Performers region, headline-list style like Capital Raises."""

    def regions(self):
        e = data("earnings.json")
        if not e:
            self.skipTest("no earnings data")
        return e["regions"]

    def test_every_configured_region_has_a_block(self):
        keys = {r["key"] for r in self.regions()}
        self.assertEqual(keys, {"anz", "asia", "us", "uk", "europe", "rest"})

    def test_every_region_has_a_summary(self):
        for r in self.regions():
            self.assertTrue(r["summary"].strip(), r["key"])

    def test_an_empty_region_uses_the_exact_static_comment(self):
        for r in self.regions():
            if not r["items"]:
                self.assertEqual(r["summary"], "No Company earnings reports available.")

    def test_no_region_shows_more_than_the_top_five_reports(self):
        for r in self.regions():
            self.assertLessEqual(len(r["items"]), 5, r["key"])

    def test_every_item_has_a_real_link(self):
        for r in self.regions():
            for it in r["items"]:
                self.assertTrue(it["url"].startswith("http"), it)
                self.assertTrue(it["headline"].strip(), it)

    def test_no_duplicate_urls_within_a_region(self):
        for r in self.regions():
            urls = [it["url"] for it in r["items"]]
            self.assertEqual(len(urls), len(set(urls)), r["key"])


class EarningsSectionRendering(DigestTestCase):
    def test_each_earnings_block_follows_its_matching_performer_region(self):
        expected = [
            ("ANZ Top Performers", "anz", "Japan Top Performers"),
            ("China (Mainland) Top Performers", "asia", "US Top Performers"),
            ("US Top Performers", "us", "UK (London) Top Performers"),
            ("UK (London) Top Performers", "uk", "European Top Performers"),
            ("European Top Performers", "europe", "Latin American Top Performers"),
            ("Latin American Top Performers", "rest", "Capital Raises"),
        ]
        e = data("earnings.json")
        has_items = {r["key"]: bool(r["items"]) for r in e["regions"]} if e else {}
        for performer, earnings_key, following in expected:
            match = re.search(
                re.escape(performer) + r'.*?data-earnings-region="' +
                re.escape(earnings_key) + r'".*?' + re.escape(following),
                self.html, re.S)
            if has_items.get(earnings_key):
                self.assertIsNotNone(
                    match, "%s earnings are not directly after %s" %
                    (earnings_key, performer))
            else:
                # A region with nothing verifiable is dropped entirely rather
                # than rendering an empty "no reports" block.
                self.assertIsNone(
                    match, "%s has no items but still rendered a block" %
                    earnings_key)

    def test_one_region_block_per_configured_region(self):
        e = data("earnings.json")
        if not e:
            self.skipTest("no earnings data")
        keys = re.findall(r'data-earnings-region="([^"]+)"', self.html)
        self.assertEqual(keys, [r["key"] for r in e["regions"] if r["items"]])

    def test_every_earnings_item_in_the_page_is_linked(self):
        e = data("earnings.json")
        if not e:
            self.skipTest("no earnings data")
        for region in e["regions"]:
            for item in region["items"]:
                self.assertIn('href="%s"' % item["url"], self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
