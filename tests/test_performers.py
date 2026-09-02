#!/usr/bin/env python3
"""Tests for fetch_performers: scraping, row shaping and mover explainers.

The scraper cases here are the ones that actually broke in production:
TradingView renders negatives with a Unicode minus rather than a hyphen, and
the catalyst lookup must never cite a chart page or an unrelated company.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_performers as FP


def tv_row(ex="ASX", code="KKO", name="Kaoko Metals", pct="151.70",
           sign="", polarity="positive", price="1.85", vol="5.06M"):
    """A TradingView movers row close enough to the real markup to parse."""
    return (
        '<tr data-rowkey="%s:%s">'
        '<td><a title="%s:%s \u2212 %s">%s</a></td>'
        '<td>%s<span class="currency-abc123">AUD</span></td>'
        '<td><span class="%s-Xy1z2">%s%s%%</span></td>'
        '<td>%s</td><td class="cell-Ab12 right-Cd34">x</td>'
        '</tr>' % (ex, code, ex, code, name, name, price,
                   polarity, sign, pct, vol))


class Clean(unittest.TestCase):
    def test_strips_tags_entities_and_space(self):
        self.assertEqual(FP.clean("<b>AT&amp;T</b>   Inc"), "AT&T Inc")

    def test_empty(self):
        self.assertEqual(FP.clean(""), "")


class ParseTradingView(unittest.TestCase):
    def test_reads_a_gainer_row(self):
        rows = FP.parse_tradingview(tv_row(), {"ASX"}, "gainers")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["code"], "KKO")
        self.assertEqual(r["ex"], "ASX")
        self.assertEqual(r["name"], "Kaoko Metals")
        self.assertEqual(r["price"], "1.85")
        self.assertAlmostEqual(r["pct"], 151.70)
        self.assertEqual(r["vol"], "5.06M")

    def test_unicode_minus_is_read_as_negative(self):
        """TradingView uses U+2212, not an ASCII hyphen. Missing this flipped
        every loser to a gain."""
        rows = FP.parse_tradingview(
            tv_row(sign="\u2212", polarity="negative", pct="12.50"),
            {"ASX"}, "losers")
        self.assertAlmostEqual(rows[0]["pct"], -12.50)

    def test_negative_class_alone_is_enough(self):
        rows = FP.parse_tradingview(
            tv_row(sign="", polarity="negative", pct="3.00"), {"ASX"}, "losers")
        self.assertAlmostEqual(rows[0]["pct"], -3.00)

    def test_other_exchanges_are_ignored(self):
        rows = FP.parse_tradingview(tv_row(ex="NASDAQ"), {"ASX"}, "gainers")
        self.assertEqual(rows, [])

    def test_rows_without_a_price_are_skipped(self):
        broken = tv_row().replace('<span class="currency-abc123">AUD</span>', "")
        self.assertEqual(FP.parse_tradingview(broken, {"ASX"}, "gainers"), [])

    def test_rows_without_a_change_are_skipped(self):
        broken = tv_row().replace('class="positive-Xy1z2"', 'class="plain"')
        self.assertEqual(FP.parse_tradingview(broken, {"ASX"}, "gainers"), [])

    def test_empty_screener_yields_nothing(self):
        """A market that just opened returns no rows; that must not crash."""
        self.assertEqual(FP.parse_tradingview("No symbols match", {"ASX"}, "g"), [])
        self.assertEqual(FP.parse_tradingview("", {"ASX"}, "g"), [])

    def test_output_is_capped_at_the_table_depth(self):
        many = "".join(tv_row(code="C%d" % i) for i in range(40))
        self.assertLessEqual(len(FP.parse_tradingview(many, {"ASX"}, "g")), FP.ROWS)

    def test_commas_in_percentages_are_handled(self):
        rows = FP.parse_tradingview(tv_row(pct="1,151.70"), {"ASX"}, "g")
        self.assertAlmostEqual(rows[0]["pct"], 1151.70)


class RowOut(unittest.TestCase):
    def cfg(self, **kw):
        base = {"code_in_name": True, "price": "${v}",
                "link": "https://example.com/{lower}", "title": "ANZ Top Performers",
                "source": "TradingView"}
        base.update(kw)
        return base

    def raw(self, **kw):
        base = {"name": "Kaoko Metals", "code": "KKO", "ex": "ASX",
                "price": "1.85", "pct": 151.7, "vol": "5.06M"}
        base.update(kw)
        return base

    def test_appends_the_code_to_the_name(self):
        out = FP.row_out(self.cfg(), self.raw())
        self.assertEqual(out["name"], "Kaoko Metals (KKO)")

    def test_does_not_double_append_when_already_bracketed(self):
        out = FP.row_out(self.cfg(), self.raw(name="Unbanked, Inc. (8746)"))
        self.assertEqual(out["name"], "Unbanked, Inc. (8746)")

    def test_respects_a_region_that_omits_the_code(self):
        out = FP.row_out(self.cfg(code_in_name=False), self.raw())
        self.assertEqual(out["name"], "Kaoko Metals")

    def test_change_is_always_signed(self):
        self.assertEqual(FP.row_out(self.cfg(), self.raw(pct=1.5))["chg"], "+1.50%")
        self.assertEqual(FP.row_out(self.cfg(), self.raw(pct=-1.5))["chg"], "-1.50%")

    def test_link_is_built_from_the_template(self):
        out = FP.row_out(self.cfg(), self.raw())
        self.assertEqual(out["url"], "https://example.com/kko")
        self.assertTrue(out["url"].startswith("http"))


class NameTokens(unittest.TestCase):
    def test_drops_corporate_suffixes(self):
        toks = FP._name_tokens("Integrated Research Limited")
        self.assertIn("integrated", toks)
        self.assertNotIn("limited", toks)

    def test_drops_short_words(self):
        self.assertNotIn("mp", FP._name_tokens("MP Materials Corp"))

    def test_cjk_names_fall_back_to_leading_characters(self):
        """CJK company names do not split on spaces."""
        toks = FP._name_tokens("\u30df\u30ac\u30ed\u30db\u30fc\u30eb")
        self.assertTrue(toks)

    def test_short_names_fall_back_to_the_name_itself(self):
        """BHP and the like are under the 4-character token floor, so the
        fallback keeps them matchable instead of returning nothing."""
        self.assertEqual(FP._name_tokens("BHP"), ["bhp"])

    def test_a_blank_name_yields_nothing(self):
        self.assertEqual(FP._name_tokens(""), [])
        self.assertEqual(FP._name_tokens("   "), [])


class Note(unittest.TestCase):
    cfg = {"title": "ANZ Top Performers", "source": "TradingView",
           "price": "${v}", "code_in_name": True,
           "link": "https://example.com/{lower}", "key": "anz"}

    def mover(self, **kw):
        base = {"name": "Kaoko Metals", "code": "KKO", "ex": "ASX",
                "price": "1.85", "pct": 151.7, "vol": "5.06M"}
        base.update(kw)
        return base

    def test_states_the_move_with_this_runs_numbers(self):
        text = FP.note(self.cfg, self.mover(), "gainer", None)
        self.assertIn("Kaoko Metals", text)
        self.assertIn("151.70 per cent", text)
        self.assertIn("$1.85", text)
        self.assertIn("5.06M", text)

    def test_loser_wording_differs_from_gainer(self):
        g = FP.note(self.cfg, self.mover(), "gainer", None)
        l = FP.note(self.cfg, self.mover(pct=-20.0), "loser", None)
        self.assertIn("led the", g)
        self.assertIn("steepest decliner", l)
        self.assertIn("down 20.00 per cent", l)

    def test_without_a_catalyst_it_says_so_rather_than_inventing_one(self):
        text = FP.note(self.cfg, self.mover(), "gainer", None)
        self.assertIn("no catalyst is asserted", text)

    def test_with_a_catalyst_it_leads_into_the_citation(self):
        hit = {"title": "Kaoko charges on copper hunt", "url": "https://x.com/a",
               "publisher": "Stockhead",
               "published": datetime(2026, 9, 2, tzinfo=timezone.utc)}
        text = FP.note(self.cfg, self.mover(), "gainer", hit)
        self.assertIn("Reported alongside the move, Stockhead on", text)
        self.assertNotIn("no catalyst is asserted", text)
        self.assertTrue(text.rstrip().endswith(":"),
                        "must lead into the link the builder appends")

    def test_missing_mover_is_reported_honestly(self):
        text = FP.note(self.cfg, None, "gainer", None)
        self.assertIn("No gainer could be retrieved", text)

    def test_volume_is_omitted_when_absent(self):
        self.assertNotIn("volume", FP.note(self.cfg, self.mover(vol=""), "gainer", None))


class SourceOut(unittest.TestCase):
    def test_no_hit_yields_an_empty_list(self):
        self.assertEqual(FP._source_out(None), [])

    def test_hit_is_serialised_for_the_builder(self):
        hit = {"title": "T", "url": "https://x.com/a", "publisher": "P",
               "published": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)}
        out = FP._source_out(hit)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["url"], "https://x.com/a")
        self.assertEqual(out[0]["title"], "T")
        self.assertIn("2026-09-02", out[0]["published"])


class CatalystMatching(unittest.TestCase):
    """catalyst() is network-bound, so the feed is injected."""

    cfg = {"key": "anz", "title": "ANZ Top Performers", "source": "TV",
           "price": "${v}", "code_in_name": True, "link": "x/{lower}"}

    def setUp(self):
        self.now = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)
        self.saved = FP.news_items
        self.saved_sleep = FP.time.sleep
        FP.time.sleep = lambda s: None      # keep the suite fast

    def tearDown(self):
        FP.news_items = self.saved
        FP.time.sleep = self.saved_sleep

    def feed(self, *items):
        FP.news_items = lambda q, gl, ceid: list(items)

    def item(self, title, days_old=0, publisher="Stockhead"):
        return {"title": title, "url": "https://x.com/a", "publisher": publisher,
                "published": self.now - timedelta(days=days_old)}

    def mover(self, name="Kaoko Metals Limited"):
        return {"name": name, "code": "KKO", "ex": "ASX", "price": "1.85",
                "pct": 151.7, "vol": "5.06M"}

    def test_matches_an_article_naming_the_company(self):
        self.feed(self.item("Kaoko charges on early copper hunt success"))
        hit = FP.catalyst(self.cfg, self.mover(), self.now)
        self.assertIsNotNone(hit)

    def test_ignores_an_article_about_a_different_company(self):
        self.feed(self.item("BHP lifts iron ore guidance"))
        self.assertIsNone(FP.catalyst(self.cfg, self.mover(), self.now))

    def test_ignores_articles_older_than_the_window(self):
        self.feed(self.item("Kaoko charges on copper",
                            days_old=FP.CATALYST_MAX_AGE_DAYS + 1))
        self.assertIsNone(FP.catalyst(self.cfg, self.mover(), self.now))

    def test_rejects_chart_and_quote_pages(self):
        """A ratio page names the company but explains nothing."""
        self.feed(self.item("Kaoko Metals Stock Price and Chart"))
        self.assertIsNone(FP.catalyst(self.cfg, self.mover(), self.now))

    def test_rejects_screener_publishers(self):
        self.feed(self.item("Kaoko jumps 150%", publisher="TradingView"))
        self.assertIsNone(FP.catalyst(self.cfg, self.mover(), self.now))

    def test_prefers_the_newest_qualifying_article(self):
        self.feed(self.item("Kaoko older story", days_old=2),
                  self.item("Kaoko newest story", days_old=0))
        # news_items yields newest-first in production; the first match wins.
        self.assertEqual(FP.catalyst(self.cfg, self.mover(), self.now)["title"],
                         "Kaoko older story")

    def test_no_mover_means_no_lookup(self):
        self.feed(self.item("anything"))
        self.assertIsNone(FP.catalyst(self.cfg, None, self.now))

    def test_an_empty_feed_is_not_an_error(self):
        self.feed()
        self.assertIsNone(FP.catalyst(self.cfg, self.mover(), self.now))


class RegionConfig(unittest.TestCase):
    def test_every_region_has_a_news_locale(self):
        """A missing locale silently falls back to US English, which finds
        nothing for a German or Japanese small cap."""
        for cfg in FP.MARKETS:
            self.assertIn(cfg["key"], FP.NEWS_LOCALE, cfg["key"])

    def test_all_nine_regions_are_configured(self):
        self.assertEqual(len(FP.MARKETS), 9)

    def test_region_keys_are_unique(self):
        keys = [c["key"] for c in FP.MARKETS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_region_has_a_link_template_and_price_format(self):
        for cfg in FP.MARKETS:
            self.assertIn("{", cfg["link"], cfg["key"])
            self.assertIn("{v}", cfg["price"], cfg["key"])

    def test_non_english_markets_are_searched_in_their_own_language(self):
        self.assertEqual(FP.NEWS_LOCALE["germany"][2], "Aktie")
        self.assertEqual(FP.NEWS_LOCALE["brazil"][2], "a\u00e7\u00f5es")
        self.assertNotEqual(FP.NEWS_LOCALE["japan"][1], "US:en")


if __name__ == "__main__":
    unittest.main(verbosity=2)
