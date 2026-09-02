#!/usr/bin/env python3
"""Tests for newsfeed: the shared Google News lookup.

Yahoo Finance's search endpoint rate-limits this environment to 429, so both
fetchers rely on Google News RSS. The noise rules are the quality gate: a
quote or chart page ranks well for any company name but explains nothing, and
citing one as a catalyst would be misleading.
"""
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import newsfeed as NF
from helpers import rss, rss_item


def item(title, publisher=""):
    return {"title": title, "publisher": publisher, "url": "u",
            "published": datetime.now(timezone.utc)}


class NoiseTitles(unittest.TestCase):
    def test_rejects_english_quote_and_chart_pages(self):
        for t in ["Acme Stock Price and Chart - TSE:1234",
                  "Acme Corp Chart | Live Quote",
                  "Acme Ltd Share Price History",
                  "Acme Dividend History and Yield"]:
            self.assertTrue(NF.is_noise(item(t)), t)

    def test_rejects_german_chart_pages(self):
        for t in ["Circus SE Aktienkurs", "ABO Energy Chart-Analyse",
                  "RWE Technische Analyse", "Bayer Kursziel 2026"]:
            self.assertTrue(NF.is_noise(item(t)), t)

    def test_rejects_cjk_quote_pages(self):
        for t in ["\u30df\u30ac\u30ed \u682a\u4fa1\u30c1\u30e3\u30fc\u30c8",
                  "8746 \u63b2\u793a\u677f",
                  "China Ecotourism \u6d41\u52a8\u6bd4\u7387 - FWB:WOR0",
                  "\u817e\u8baf \u884c\u60c5"]:
            self.assertTrue(NF.is_noise(item(t)), t)

    def test_rejects_portuguese_quote_pages(self):
        self.assertTrue(NF.is_noise(item("Casas Bahia Cota\u00e7\u00f5es")))

    def test_matching_is_case_insensitive(self):
        self.assertTrue(NF.is_noise(item("ACME STOCK PRICE AND CHART")))


class NoisePublishers(unittest.TestCase):
    def test_rejects_screener_and_broker_pages(self):
        for p in ["TradingView", "Moomoo", "Investing.com", "MarketScreener",
                  "Simply Wall St", "wallmine", "stockinvest.us"]:
            self.assertTrue(NF.is_noise(item("Acme jumps 40%", p)), p)

    def test_publisher_match_ignores_case_and_space(self):
        self.assertTrue(NF.is_noise(item("Acme jumps", "  tradingview  ")))


class GenuineReporting(unittest.TestCase):
    def test_keeps_real_articles(self):
        for t, p in [
            ("Resources Top 5: Kaoko charges on early copper hunt success",
             "Stockhead"),
            ("A\u00e7\u00f5es da Casas Bahia disparam 65%", "UOL Economia"),
            ("Circus SE: Aktie notiert bei 3,58 Euro nach Start der Pods",
             "AD HOC NEWS"),
            ("BWXT Rises as Army Janus Win Supports Nuclear Growth",
             "Seeking Alpha"),
        ]:
            self.assertFalse(NF.is_noise(item(t, p)), t)

    def test_a_price_move_headline_is_not_noise(self):
        self.assertFalse(NF.is_noise(item("Gold slips 0.7% as dollar firms",
                                          "Reuters")))


class NewsItemsParsing(unittest.TestCase):
    """news_items is network-bound; the HTTP layer is mocked."""

    def fetch(self, body, status=200):
        resp = mock.Mock(status_code=status, content=body.encode())
        resp.raise_for_status = mock.Mock()
        with mock.patch.object(NF.requests, "get", return_value=resp):
            return NF.news_items("q")

    def test_parses_title_link_date_and_publisher(self):
        x = rss([("<item><title>Gold slips</title>"
                  "<link>https://ex.com/g</link>"
                  "<pubDate>Wed, 02 Sep 2026 08:00:00 GMT</pubDate>"
                  "<source url='https://ex.com'>Reuters</source></item>")])
        got = self.fetch(x)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["title"], "Gold slips")
        self.assertEqual(got[0]["url"], "https://ex.com/g")
        self.assertEqual(got[0]["publisher"], "Reuters")

    def test_results_come_back_newest_first(self):
        x = rss([
            rss_item(title="older", date="Mon, 31 Aug 2026 08:00:00 GMT"),
            rss_item(title="newer", date="Wed, 02 Sep 2026 08:00:00 GMT"),
        ])
        self.assertEqual([i["title"] for i in self.fetch(x)], ["newer", "older"])

    def test_items_missing_a_title_or_link_are_dropped(self):
        self.assertEqual(self.fetch(rss([rss_item(title=None)])), [])
        self.assertEqual(self.fetch(rss([rss_item(link=None)])), [])

    def test_items_with_an_unparseable_date_are_dropped(self):
        self.assertEqual(self.fetch(rss([rss_item(date="not a date")])), [])

    def test_dates_are_timezone_aware(self):
        got = self.fetch(rss([rss_item()]))
        self.assertIsNotNone(got[0]["published"].tzinfo)

    def test_malformed_xml_returns_empty_not_an_exception(self):
        self.assertEqual(self.fetch("<rss><channel><item>"), [])

    def test_a_network_error_returns_empty(self):
        """A failed lookup must degrade to "no catalyst", never break the run."""
        with mock.patch.object(NF.requests, "get",
                               side_effect=OSError("connection reset")):
            self.assertEqual(NF.news_items("q"), [])

    def test_an_http_error_returns_empty(self):
        resp = mock.Mock()
        resp.raise_for_status = mock.Mock(side_effect=Exception("429"))
        with mock.patch.object(NF.requests, "get", return_value=resp):
            self.assertEqual(NF.news_items("q"), [])


class QueryConstruction(unittest.TestCase):
    def test_locale_and_query_reach_the_url(self):
        resp = mock.Mock(content=rss([]).encode())
        resp.raise_for_status = mock.Mock()
        with mock.patch.object(NF.requests, "get", return_value=resp) as g:
            NF.news_items("gold price", gl="DE", ceid="DE:de")
            url = g.call_args[0][0]
        self.assertIn("gold%20price", url)
        self.assertIn("gl=DE", url)
        self.assertIn("ceid=DE:de", url)

    def test_special_characters_are_encoded(self):
        resp = mock.Mock(content=rss([]).encode())
        resp.raise_for_status = mock.Mock()
        with mock.patch.object(NF.requests, "get", return_value=resp) as g:
            NF.news_items('"Acme & Co" Aktie')
            url = g.call_args[0][0]
        self.assertNotIn(" ", url)
        self.assertIn("%26", url)


if __name__ == "__main__":
    unittest.main(verbosity=2)
