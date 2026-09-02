#!/usr/bin/env python3
"""Tests for feedlib: the RSS/Atom parsing shared by every news fetcher.

A parsing regression here silently empties an outlet section rather than
failing loudly, so the edge cases that actually appear in these feeds are
pinned down: CDATA, Atom href links, named timezones, fractional seconds.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import feedlib as FL
from helpers import rss, rss_item


class StripHtml(unittest.TestCase):
    def test_removes_tags_and_collapses_space(self):
        self.assertEqual(FL.strip_html("<p>Hello   <b>world</b></p>"), "Hello world")

    def test_unescapes_entities(self):
        self.assertEqual(FL.strip_html("AT&amp;T &#8212; up"), "AT&T \u2014 up")

    def test_empty_input_is_empty_string(self):
        self.assertEqual(FL.strip_html(None), "")
        self.assertEqual(FL.strip_html(""), "")


class ParseDate(unittest.TestCase):
    def test_rfc822_with_numeric_offset(self):
        d = FL._parse_date("Wed, 02 Sep 2026 08:00:00 +1000")
        self.assertEqual(d.utcoffset(), timedelta(hours=10))

    def test_named_zone_is_translated(self):
        """strptime's %Z will not take these, so feedlib maps them itself."""
        self.assertEqual(FL._parse_date("Wed, 02 Sep 2026 08:00:00 GMT").utcoffset(),
                         timedelta(0))
        self.assertEqual(FL._parse_date("Wed, 02 Sep 2026 08:00:00 AEST").utcoffset(),
                         timedelta(hours=10))

    def test_iso_with_fractional_seconds(self):
        """CNN's sitemap emits 2026-08-30T16:01:57.933Z."""
        self.assertIsNotNone(FL._parse_date("2026-08-30T16:01:57.933Z"))

    def test_iso_with_colon_in_offset(self):
        self.assertIsNotNone(FL._parse_date("2026-08-30T16:01:57+10:00"))

    def test_naive_dates_are_treated_as_utc(self):
        d = FL._parse_date("2026-08-30T16:01:57Z")
        self.assertEqual(d.tzinfo, timezone.utc)

    def test_unparseable_returns_none(self):
        for bad in (None, "", "yesterday", "32 Foo 2026"):
            self.assertIsNone(FL._parse_date(bad), bad)


class ParseFeed(unittest.TestCase):
    def test_reads_a_basic_rss_item(self):
        items = FL.parse_feed(rss([rss_item()]))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "A headline")
        self.assertEqual(items[0]["url"], "https://example.com/a")
        self.assertIsNotNone(items[0]["date"])

    def test_reads_cdata_titles(self):
        x = rss([rss_item(title="<![CDATA[Markets & the Fed]]>")])
        self.assertEqual(FL.parse_feed(x)[0]["title"], "Markets & the Fed")

    def test_reads_atom_entries_with_href_links(self):
        atom = ('<feed><entry><title>Atom story</title>'
                '<link rel="alternate" href="https://example.com/atom"/>'
                '<updated>2026-09-02T08:00:00Z</updated></entry></feed>')
        items = FL.parse_feed(atom)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://example.com/atom")

    def test_reads_atom_links_with_single_quoted_href(self):
        """Valid XML; matching only double quotes silently emptied such feeds."""
        atom = ("<feed><entry><title>Atom story</title>"
                "<link rel='alternate' href='https://example.com/atom'/>"
                "<updated>2026-09-02T08:00:00Z</updated></entry></feed>")
        items = FL.parse_feed(atom)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://example.com/atom")

    def test_items_without_a_usable_link_are_dropped(self):
        """A headline with no URL breaks the every-item-is-clickable rule."""
        self.assertEqual(FL.parse_feed(rss([rss_item(link=None)])), [])
        self.assertEqual(FL.parse_feed(rss([rss_item(link="/relative/path")])), [])

    def test_items_without_a_title_are_dropped(self):
        self.assertEqual(FL.parse_feed(rss([rss_item(title=None)])), [])

    def test_link_filter_rejects_foreign_domains(self):
        x = rss([rss_item(link="https://example.com/a"),
                 rss_item(link="https://cnn.com/2026/story")])
        items = FL.parse_feed(x, link_must_match=r"cnn\.com")
        self.assertEqual(len(items), 1)
        self.assertIn("cnn.com", items[0]["url"])

    def test_empty_or_missing_xml_is_empty_list(self):
        self.assertEqual(FL.parse_feed(None), [])
        self.assertEqual(FL.parse_feed(""), [])

    def test_undated_item_still_parses(self):
        items = FL.parse_feed(rss([rss_item(date=None)]))
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["date"])


class ParseNewsSitemap(unittest.TestCase):
    def sitemap(self, loc, title, date="2026-09-02T08:00:00Z"):
        return ("<urlset><url><loc>%s</loc>"
                "<news:title>%s</news:title>"
                "<news:publication_date>%s</news:publication_date>"
                "</url></urlset>" % (loc, title, date))

    def test_reads_loc_and_title(self):
        items = FL.parse_news_sitemap(
            self.sitemap("https://cnn.com/2026/09/02/x", "Sitemap story"))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://cnn.com/2026/09/02/x")
        self.assertEqual(items[0]["title"], "Sitemap story")

    def test_link_filter_applies(self):
        x = self.sitemap("https://other.com/x", "Nope")
        self.assertEqual(FL.parse_news_sitemap(x, link_must_match=r"cnn\.com"), [])

    def test_empty_input(self):
        self.assertEqual(FL.parse_news_sitemap(None), [])


class Recent(unittest.TestCase):
    def item(self, days_old):
        d = None if days_old is None else \
            datetime.now(timezone.utc) - timedelta(days=days_old)
        return {"title": "t", "url": "u", "detail": "", "date": d}

    def test_keeps_fresh_drops_old(self):
        got = FL.recent([self.item(0), self.item(1), self.item(10)], max_days=3)
        self.assertEqual(len(got), 2)

    def test_undated_items_are_kept(self):
        """Dropping undated items would empty feeds that omit pubDate."""
        self.assertEqual(len(FL.recent([self.item(None)], max_days=3)), 1)

    def test_boundary_is_inclusive_enough(self):
        self.assertEqual(len(FL.recent([self.item(2.9)], max_days=3)), 1)


class Trim(unittest.TestCase):
    def test_short_text_is_untouched(self):
        self.assertEqual(FL.trim("A short line."), "A short line.")

    def test_strips_boilerplate_tails(self):
        self.assertNotIn("Continue reading", FL.trim("Real detail. Continue reading"))
        self.assertNotIn("The post", FL.trim("Real detail. The post appeared first"))

    def test_long_text_is_cut_at_a_sentence_when_possible(self):
        text = ("First sentence that is comfortably long enough to pass the "
                "threshold. " + "tail words " * 40)
        out = FL.trim(text, limit=240)
        self.assertTrue(len(out) <= 240)
        self.assertTrue(out.endswith("."))

    def test_long_text_without_a_sentence_break_gets_an_ellipsis(self):
        out = FL.trim("word " * 200, limit=100)
        self.assertTrue(out.endswith("\u2026"))
        self.assertTrue(len(out) <= 101)

    def test_empty_input(self):
        self.assertEqual(FL.trim(""), "")
        self.assertEqual(FL.trim(None), "")


class Dedupe(unittest.TestCase):
    def item(self, title, url):
        return {"title": title, "url": url, "detail": "", "date": None}

    def test_same_url_is_dropped(self):
        seen_u, seen_t = set(), set()
        got = FL.dedupe([self.item("A", "u1"), self.item("B", "u1")], seen_u, seen_t)
        self.assertEqual(len(got), 1)

    def test_same_title_different_url_is_dropped(self):
        """The same story syndicated under two URLs must not appear twice."""
        seen_u, seen_t = set(), set()
        got = FL.dedupe([self.item("Fed holds rates", "u1"),
                         self.item("Fed  holds  rates!", "u2")], seen_u, seen_t)
        self.assertEqual(len(got), 1)

    def test_state_carries_across_calls(self):
        seen_u, seen_t = set(), set()
        FL.dedupe([self.item("A", "u1")], seen_u, seen_t)
        self.assertEqual(FL.dedupe([self.item("A", "u2")], seen_u, seen_t), [])

    def test_distinct_items_all_survive(self):
        seen_u, seen_t = set(), set()
        got = FL.dedupe([self.item("A", "u1"), self.item("B", "u2")], seen_u, seen_t)
        self.assertEqual(len(got), 2)


class Provenance(unittest.TestCase):
    def test_datetime_dates_are_isoformatted(self):
        p = FL.provenance({"date": datetime(2026, 9, 2, tzinfo=timezone.utc)}, "src")
        self.assertTrue(p["published"].startswith("2026-09-02"))
        self.assertEqual(p["source_url"], "src")
        self.assertIn("T", p["fetched"])

    def test_string_dates_are_parsed_not_passed_through(self):
        """A raw string would break the downstream timestamp column."""
        p = FL.provenance({"date": "Wed, 02 Sep 2026 08:00:00 GMT"}, "src")
        self.assertTrue(p["published"].startswith("2026-09-02"))

    def test_unparseable_string_becomes_none(self):
        self.assertIsNone(FL.provenance({"date": "not a date"}, "src")["published"])

    def test_missing_date_becomes_none(self):
        self.assertIsNone(FL.provenance({}, "src")["published"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
