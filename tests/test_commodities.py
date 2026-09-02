#!/usr/bin/env python3
"""Tests for the commodities fetcher.

Covers the three defects fixed together: a summary paragraph that never
changed, an invented rare-earths fallback price, and a stale-flag stub that
never fired. Run with:  python3 -m unittest discover -s tests -v

Stdlib unittest, because pytest is not installed in this environment. Nothing
here touches the network - the fetchers are exercised through injected data.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetch_commodities as FC


def row(name, chg, price="100", unit="USD/T", flag=None):
    r = {"name": name, "chg": chg, "price": price, "unit": unit}
    if flag:
        r["flag"] = flag
    return r


class ParseDescDate(unittest.TestCase):
    def test_reads_the_quote_date(self):
        self.assertEqual(FC._parse_desc_date("August 27, 2026"), "2026-08-27")

    def test_reads_a_date_with_trailing_text(self):
        self.assertEqual(FC._parse_desc_date("on September 1, 2026, down"),
                         "2026-09-01")

    def test_returns_none_for_junk(self):
        for bad in ("", None, "not a date", "Smarch 40, 2026"):
            self.assertIsNone(FC._parse_desc_date(bad), bad)


class StaleFlag(unittest.TestCase):
    """The stub this replaces returned None unconditionally, so nothing was
    ever flagged - which is why Cobalt sat at 0.00% for six runs undisclosed."""

    today = date(2026, 9, 2)

    def test_todays_quote_is_not_stale(self):
        self.assertIsNone(FC._stale_flag("2026-09-02", self.today))

    def test_yesterdays_quote_is_not_stale(self):
        self.assertIsNone(FC._stale_flag("2026-09-01", self.today))

    def test_two_days_back_is_stale(self):
        self.assertEqual(FC._stale_flag("2026-08-31", self.today), "stale")

    def test_a_week_back_is_stale(self):
        self.assertEqual(FC._stale_flag("2026-08-26", self.today), "stale")

    def test_missing_or_unparseable_date_does_not_flag(self):
        self.assertIsNone(FC._stale_flag(None, self.today))
        self.assertIsNone(FC._stale_flag("nonsense", self.today))


class Pct(unittest.TestCase):
    def test_parses_signed_percentages(self):
        self.assertAlmostEqual(FC._pct(row("x", "+2.19%")), 2.19)
        self.assertAlmostEqual(FC._pct(row("x", "-0.24%")), -0.24)
        self.assertAlmostEqual(FC._pct(row("x", "0.00%")), 0.0)

    def test_bad_input_is_zero_not_an_error(self):
        self.assertEqual(FC._pct({"chg": "n/a"}), 0.0)
        self.assertEqual(FC._pct({}), 0.0)


class FamilyClause(unittest.TestCase):
    def test_all_higher_reads_as_across_the_board(self):
        c = FC._family_clause("energy", [row("WTI", "+1.0%"), row("Brent", "+2.0%")])
        self.assertIn("energy advanced across the board", c)
        self.assertIn("Brent", c)          # named after the biggest move

    def test_all_lower_reads_as_across_the_board(self):
        c = FC._family_clause("base metals", [row("Copper", "-1.0%")])
        self.assertIn("fell across the board", c)

    def test_mixed_reports_the_split(self):
        c = FC._family_clause("energy", [row("WTI", "+1.0%"), row("Brent", "-2.0%")])
        self.assertIn("energy was mixed, 1 of 2 higher", c)
        self.assertIn("Brent", c)

    def test_mixed_family_does_not_claim_the_outlier_led_it(self):
        """A decliner must not be described as leading a mostly-higher family."""
        c = FC._family_clause("precious metals",
                              [row("Gold", "+0.1%"), row("Silver", "+0.2%"),
                               row("Platinum", "-1.14%")], "were")
        self.assertIn("precious metals were mixed, 2 of 3 higher", c)
        self.assertIn("the biggest move coming from Platinum", c)
        self.assertNotIn("led by", c)

    def test_uniform_family_still_reads_as_led_by(self):
        c = FC._family_clause("energy", [row("WTI", "+1.0%"), row("Brent", "+2.0%")])
        self.assertIn("led by Brent", c)

    def test_plural_families_use_a_plural_verb(self):
        c = FC._family_clause("base metals", [row("Cu", "+1%"), row("Zn", "-1%")],
                              "were")
        self.assertIn("base metals were mixed", c)
        self.assertNotIn("base metals was", c)

    def test_all_flat_is_described_as_unchanged(self):
        c = FC._family_clause("bulk", [row("Cobalt", "0.00%")])
        self.assertIn("unchanged", c)
        self.assertNotIn("led by", c)

    def test_empty_family_yields_nothing(self):
        self.assertIsNone(FC._family_clause("energy", []))


class BuildSummary(unittest.TestCase):
    now = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)

    def sample(self):
        return [row("Petroleum (WTI)", "+1.20%", "83.44", "USD/Bbl"),
                row("Brent Crude", "+0.80%", "86.10", "USD/Bbl"),
                row("Gold", "-0.12%", "4322.60", "USD/t oz"),
                row("Copper", "+3.00%", "4.51", "USD/Lbs"),
                row("Cobalt", "0.00%", "56290", "USD/T")]

    def test_paragraph_reflects_the_actual_tally(self):
        text = FC.build_summary(self.sample(), self.now)
        self.assertIn("3 of the 5 tracked benchmarks higher", text)
        self.assertIn("1 lower", text)

    def test_paragraph_names_the_biggest_mover(self):
        text = FC.build_summary(self.sample(), self.now)
        self.assertIn("largest single move", text)
        self.assertIn("Copper", text)

    def test_different_prices_produce_a_different_paragraph(self):
        """The regression this suite exists for: the old summary was a constant."""
        a = FC.build_summary(self.sample(), self.now)
        flipped = [dict(r, chg="-" + r["chg"].lstrip("+"))
                   for r in self.sample() if r["chg"] != "0.00%"]
        b = FC.build_summary(flipped, self.now)
        self.assertNotEqual(a, b)

    def test_tone_tracks_the_balance(self):
        up = [row("a", "+1%"), row("b", "+2%"), row("c", "-1%")]
        down = [row("a", "-1%"), row("b", "-2%"), row("c", "+1%")]
        self.assertIn("broadly firmer", FC.build_summary(up, self.now))
        self.assertIn("broadly weaker", FC.build_summary(down, self.now))

    def test_stale_rows_are_disclosed_in_the_prose(self):
        rows = self.sample()
        rows[4] = row("Cobalt", "0.00%", "56290", "USD/T", flag="stale")
        text = FC.build_summary(rows, self.now)
        self.assertIn("Cobalt", text)
        self.assertIn("not refreshed past the prior day", text)

    def test_no_stale_disclosure_when_nothing_is_stale(self):
        self.assertNotIn("not refreshed past the prior day",
                         FC.build_summary(self.sample(), self.now))

    def test_empty_input_admits_it_rather_than_inventing(self):
        text = FC.build_summary([], self.now)
        self.assertIn("No commodity prices could be retrieved", text)
        self.assertNotIn("broadly", text)

    def test_article_citation_is_appended_when_present(self):
        article = {"title": "Gold slips", "url": "https://example.com/g",
                   "publisher": "Reuters",
                   "published": datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc)}
        text = FC.build_summary(self.sample(), self.now, article)
        self.assertIn("Reported alongside the session, Reuters on", text)

    def test_summary_is_not_the_retired_placeholder(self):
        self.assertNotIn("Commodity markets are mixed in the latest session",
                         FC.build_summary(self.sample(), self.now))


class RareEarthsFallback(unittest.TestCase):
    """The proxy used to fall back to a hardcoded 62.20 at +0.00%."""

    def test_no_invented_price_remains_in_the_source(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "fetch_commodities.py")) as f:
            code = [ln for ln in f if not ln.lstrip().startswith("#")]
        self.assertNotIn("62.20", "".join(code))


class MainIntegration(unittest.TestCase):
    """main() end to end with every network call stubbed out."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = {n: getattr(FC, n) for n in
                      ("D", "_mp_materials_proxy", "_parse_kitco",
                       "_parse_tradingeconomics", "_market_article")}
        FC.D = self.tmp
        FC._market_article = lambda now: None
        FC._parse_kitco = lambda slug: None

    def tearDown(self):
        for n, v in self.saved.items():
            setattr(FC, n, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_main(self):
        FC.main()
        with open(os.path.join(self.tmp, "commodities.json")) as f:
            return json.load(f)

    def test_rare_earths_is_dropped_when_the_proxy_fails(self):
        FC._mp_materials_proxy = lambda: None
        FC._parse_tradingeconomics = lambda slug: {
            "price": "10", "chg": "+1.00%", "asof": date.today().isoformat()}
        out = self.run_main()
        names = [r["name"] for r in out["commodities"]]
        self.assertNotIn("Rare Earth Elements", names)
        self.assertEqual(len(names), len(FC.COMMODITIES) - 1)
        self.assertNotIn("62.20", json.dumps(out))

    def test_rare_earths_is_published_when_the_proxy_works(self):
        FC._mp_materials_proxy = lambda: {
            "price": "71.55", "chg": "+2.00%", "flag": "proxy",
            "url": "https://finance.yahoo.com/quote/MP"}
        FC._parse_tradingeconomics = lambda slug: {
            "price": "10", "chg": "+1.00%", "asof": date.today().isoformat()}
        out = self.run_main()
        re_row = [r for r in out["commodities"] if r["name"] == "Rare Earth Elements"]
        self.assertEqual(len(re_row), 1)
        self.assertEqual(re_row[0]["price"], "71.55")
        self.assertEqual(re_row[0]["flag"], "proxy")

    def test_a_stale_source_date_flags_the_row_and_the_prose(self):
        old = (date.today() - timedelta(days=9)).isoformat()
        FC._mp_materials_proxy = lambda: None
        FC._parse_tradingeconomics = lambda slug: {
            "price": "10", "chg": "0.00%", "asof": old}
        out = self.run_main()
        self.assertTrue(all(r["flag"] == "stale" for r in out["commodities"]))
        self.assertIn("not refreshed past the prior day", out["summary"])

    def test_summary_changes_when_the_prices_change(self):
        FC._mp_materials_proxy = lambda: None
        today = date.today().isoformat()
        FC._parse_tradingeconomics = lambda slug: {
            "price": "10", "chg": "+1.00%", "asof": today}
        first = self.run_main()["summary"]
        FC._parse_tradingeconomics = lambda slug: {
            "price": "10", "chg": "-4.00%", "asof": today}
        second = self.run_main()["summary"]
        self.assertNotEqual(first, second)
        self.assertIn("broadly firmer", first)
        self.assertIn("broadly weaker", second)

    def test_total_fetch_failure_yields_no_rows_and_an_honest_summary(self):
        FC._mp_materials_proxy = lambda: None
        FC._parse_tradingeconomics = lambda slug: None
        out = self.run_main()
        self.assertEqual(out["commodities"], [])
        self.assertIn("No commodity prices could be retrieved", out["summary"])


class TradingEconomicsParser(unittest.TestCase):
    def test_description_shapes_are_understood(self):
        import re
        pat = (r"([A-Za-z\s]+?)\s+(fell|rose|traded flat)\s+(?:to|at)\s+"
               r"([0-9,.]+)\s+([A-Za-z/\.\s]+?)\s+on\s+(.+?),\s*"
               r"(?:(down|up)\s+([0-9.]+)%|traded flat)")
        for desc, price in [
            ("Crude Oil fell to 83.44 USD/Bbl on August 28, 2026, down 0.11% "
             "from the previous day.", "83.44"),
            ("Coal rose to 139.75 USD/T on August 28, 2026, up 0.18% from the "
             "previous day.", "139.75"),
        ]:
            m = re.search(pat, desc)
            self.assertIsNotNone(m, desc)
            self.assertEqual(m.group(3), price)


class NewsfeedNoise(unittest.TestCase):
    """Quote and chart pages must never be cited as a catalyst."""

    def setUp(self):
        import newsfeed
        self.nf = newsfeed

    def item(self, title, publisher=""):
        return {"title": title, "publisher": publisher, "url": "u",
                "published": datetime.now(timezone.utc)}

    def test_rejects_chart_and_quote_pages(self):
        for t in ["Acme Stock Price and Chart - TSE:1234",
                  "Acme \u682a\u4fa1\u30c1\u30e3\u30fc\u30c8 - Yahoo",
                  "Acme AG Chart-Analyse | Trading",
                  "Acme Ltd \u6d41\u52a8\u6bd4\u7387 - FWB"]:
            self.assertTrue(self.nf.is_noise(self.item(t)), t)

    def test_rejects_screener_publishers(self):
        self.assertTrue(self.nf.is_noise(self.item("Acme up 10%", "TradingView")))
        self.assertTrue(self.nf.is_noise(self.item("Acme up 10%", "Moomoo")))

    def test_keeps_genuine_reporting(self):
        for t, p in [("Acme surges on copper discovery", "Stockhead"),
                     ("A\u00e7\u00f5es da Casas Bahia disparam 65%", "UOL Economia")]:
            self.assertFalse(self.nf.is_noise(self.item(t, p)), t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
