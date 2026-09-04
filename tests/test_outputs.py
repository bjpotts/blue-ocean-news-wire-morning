#!/usr/bin/env python3
"""Tests for the delivery layer: PDF naming, email attachment choice and the
capital-raise summaries.

The email tests exist because a run once built the page but never sent the
mail. The attachment must be the full report, chosen deterministically.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_capraises as CR
import fetch_earnings as EG
import tempfile
from pathlib import Path

from helpers import load_from_source, source_of


class CapitalRaiseSummaries(unittest.TestCase):
    def item(self, headline):
        return {"headline": headline, "url": "https://x.com/a", "detail": ""}

    def test_an_empty_region_is_reported_honestly(self):
        text = CR.summarise("Europe", [])
        self.assertIn("nothing is listed", text)
        self.assertIn("Europe", text)

    def test_a_single_item_is_described_as_one(self):
        text = CR.summarise("UK", [self.item("Acme raises 50m")])
        self.assertIn("A single verifiable", text)
        self.assertIn("Acme raises 50m", text)

    def test_several_items_are_counted_and_led_by_the_first(self):
        items = [self.item("Big deal"), self.item("Second"), self.item("Third")]
        text = CR.summarise("ANZ", items)
        self.assertIn("3 items", text)
        self.assertIn("led by Big deal", text)

    def test_the_summary_changes_with_the_items(self):
        """It must reflect the run, not be boilerplate per region."""
        a = CR.summarise("US", [self.item("Deal A"), self.item("B")])
        b = CR.summarise("US", [self.item("Deal Z"), self.item("B")])
        self.assertNotEqual(a, b)

    def test_the_region_is_always_named(self):
        for n in (0, 1, 3):
            text = CR.summarise("Asia", [self.item("x")] * n)
            self.assertIn("Asia", text)

    def test_a_fully_repeated_region_says_so_honestly(self):
        """This is the guard against a region silently freezing on the same
        headline run after run: if nothing fresh was found, say so."""
        text = CR.summarise("ANZ", [self.item("Old news")], fresh_count=0)
        self.assertIn("No newer capital markets item", text)

    def test_a_partly_fresh_region_carries_no_stale_note(self):
        text = CR.summarise("ANZ", [self.item("New"), self.item("Old")],
                            fresh_count=1)
        self.assertNotIn("No newer capital markets item", text)

    def test_fresh_count_defaults_to_no_stale_note(self):
        """Existing callers that don't pass fresh_count must see unchanged
        behaviour."""
        text = CR.summarise("ANZ", [self.item("Item")])
        self.assertNotIn("No newer capital markets item", text)


class CapitalRaiseRotation(unittest.TestCase):
    """A region must prefer a fresh headline over repeating what the last
    edition already carried, and fall back to a repeat only when nothing
    fresh exists - see fetch_capraises.main()."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "capraises.json")

    def write_prev(self, regions):
        import json
        with open(self.path, "w") as f:
            json.dump({"regions": regions}, f)

    def test_missing_file_yields_no_prior_urls(self):
        self.assertEqual(CR._load_prev_urls(self.path), {})

    def test_corrupt_file_yields_no_prior_urls_rather_than_raising(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(CR._load_prev_urls(self.path), {})

    def test_prior_urls_are_read_per_region(self):
        self.write_prev([
            {"key": "anz", "items": [{"url": "https://x.com/a"},
                                     {"url": "https://x.com/b"}]},
            {"key": "us", "items": [{"url": "https://x.com/c"}]},
        ])
        prev = CR._load_prev_urls(self.path)
        self.assertEqual(prev["anz"], {"https://x.com/a", "https://x.com/b"})
        self.assertEqual(prev["us"], {"https://x.com/c"})

    def test_a_region_absent_from_the_prior_file_has_no_prior_urls(self):
        self.write_prev([{"key": "anz", "items": [{"url": "https://x.com/a"}]}])
        prev = CR._load_prev_urls(self.path)
        self.assertNotIn("uk", prev)


class EarningsSummaries(unittest.TestCase):
    """fetch_earnings.summarise() mirrors fetch_capraises.summarise() -
    same honesty rules, different subject matter."""

    def item(self, headline):
        return {"headline": headline, "url": "https://x.com/a", "detail": ""}

    def test_an_empty_region_uses_the_exact_static_comment(self):
        text = EG.summarise("Europe", [])
        self.assertEqual(text, "No Company earnings reports available.")

    def test_a_single_item_is_described_as_one(self):
        text = EG.summarise("UK", [self.item("Acme posts full-year profit")])
        self.assertIn("A single verifiable", text)
        self.assertIn("Acme posts full-year profit", text)

    def test_several_items_are_counted_and_led_by_the_first(self):
        items = [self.item("Big result"), self.item("Second"), self.item("Third")]
        text = EG.summarise("ANZ", items)
        self.assertIn("3 items", text)
        self.assertIn("led by Big result", text)

    def test_a_stale_region_discloses_the_carry_forward(self):
        text = EG.summarise("ANZ", [self.item("Old"), self.item("Older")],
                            fresh_count=0)
        self.assertIn("No newer earnings item", text)

    def test_a_partly_fresh_region_carries_no_stale_note(self):
        text = EG.summarise("ANZ", [self.item("New"), self.item("Old")],
                            fresh_count=1)
        self.assertNotIn("No newer earnings item", text)


class EarningsRotation(unittest.TestCase):
    """Same fresh-over-repeat preference as Capital Raises, applied to the
    Market Earnings Reporting section - see fetch_earnings.main()."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "earnings.json")

    def write_prev(self, regions):
        import json
        with open(self.path, "w") as f:
            json.dump({"regions": regions}, f)

    def test_missing_file_yields_no_prior_urls(self):
        self.assertEqual(EG._load_prev_urls(self.path), {})

    def test_corrupt_file_yields_no_prior_urls_rather_than_raising(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(EG._load_prev_urls(self.path), {})

    def test_prior_urls_are_read_per_region(self):
        self.write_prev([
            {"key": "anz", "items": [{"url": "https://x.com/a"},
                                     {"url": "https://x.com/b"}]},
            {"key": "us", "items": [{"url": "https://x.com/c"}]},
        ])
        prev = EG._load_prev_urls(self.path)
        self.assertEqual(prev["anz"], {"https://x.com/a", "https://x.com/b"})
        self.assertEqual(prev["us"], {"https://x.com/c"})

    def test_a_region_absent_from_the_prior_file_has_no_prior_urls(self):
        self.write_prev([{"key": "anz", "items": [{"url": "https://x.com/a"}]}])
        prev = EG._load_prev_urls(self.path)
        self.assertNotIn("uk", prev)


class PdfNaming(unittest.TestCase):
    """The scheduler and the email step agree on this filename shape."""

    def setUp(self):
        self.M = load_from_source("make_pdf.py",
                                  ["edition_suffix", "output_path", "ROOT", "PREVIEW"])
        self.tmp = tempfile.mkdtemp()

    def preview(self, chip):
        path = Path(self.tmp) / "preview.html"
        path.write_text('<span class="edition-chip">%s</span>' % chip)
        self.M["PREVIEW"] = path
        # rebind the closure's module global
        self.M["edition_suffix"].__globals__["PREVIEW"] = path

    def test_morning_edition_yields_am(self):
        self.preview("Morning Edition")
        self.assertEqual(self.M["edition_suffix"](), "am")

    def test_evening_edition_yields_pm(self):
        self.preview("Evening Edition")
        self.assertEqual(self.M["edition_suffix"](), "pm")

    def test_the_chip_is_matched_case_insensitively(self):
        self.preview("MORNING EDITION")
        self.assertEqual(self.M["edition_suffix"](), "am")

    def test_the_filename_carries_the_date_and_edition(self):
        self.preview("Evening Edition")
        name = self.M["output_path"]().name
        self.assertRegex(name, r"^market-wrap-up-\d{4}-\d{2}-\d{2}-pm\.pdf$")

    def test_the_pattern_matches_what_the_emailer_globs(self):
        pattern = re.compile(r"market-wrap-up-\d{4}-\d{2}-\d{2}-(am|pm)\.pdf")
        for name in ("market-wrap-up-2026-09-02-pm.pdf",
                     "market-wrap-up-2026-09-02-am.pdf"):
            self.assertRegex(name, pattern)
        self.assertNotRegex("market-wrap-up-snapshot.pdf", pattern)


class EmailDelivery(unittest.TestCase):
    def setUp(self):
        self.src = source_of(os.path.join("scripts", "send_email.py"))

    def test_it_attaches_the_full_report_not_a_snapshot(self):
        self.assertIn("market-wrap-up-*.pdf", self.src)
        self.assertNotIn("snapshot", self.src.lower())

    def test_the_newest_pdf_is_chosen_deterministically(self):
        self.assertIn("sorted(", self.src)

    def test_the_recipient_is_the_standing_address(self):
        self.assertIn("bjpotts@gmail.com", self.src)

    def test_a_missing_pdf_is_an_error_not_a_silent_skip(self):
        """A run that builds the page but sends nothing must be loud."""
        self.assertIn("No full PDF found", self.src)
        self.assertRegex(self.src, r"return 1|sys\.exit\(1\)")

    def test_latest_pdf_picks_the_newest_and_none_when_empty(self):
        E = load_from_source(os.path.join("scripts", "send_email.py"),
                             ["latest_pdf", "BASE"])
        tmp = tempfile.mkdtemp()
        E["latest_pdf"].__globals__["BASE"] = tmp
        self.assertIsNone(E["latest_pdf"]())
        for n in ("market-wrap-up-2026-09-01-pm.pdf",
                  "market-wrap-up-2026-09-02-am.pdf"):
            Path(tmp, n).write_bytes(b"%PDF-1.4")
        self.assertTrue(E["latest_pdf"]().endswith("2026-09-02-am.pdf"))

    def test_the_subject_is_fixed_for_this_edition(self):
        self.assertRegex(self.src, r"SUBJECT\s*=")

    def test_glob_ordering_picks_the_latest_date(self):
        names = ["market-wrap-up-2026-09-01-pm.pdf",
                 "market-wrap-up-2026-09-02-am.pdf",
                 "market-wrap-up-2026-08-31-pm.pdf"]
        self.assertEqual(sorted(names)[-1], "market-wrap-up-2026-09-02-am.pdf")


class SchedulerContract(unittest.TestCase):
    def test_the_runner_stops_on_a_failed_step(self):
        """Without this the emailer would send yesterday's PDF after a failed
        build."""
        src = source_of(os.path.join("scripts", "run_daily.sh"))
        self.assertRegex(src, r"set -[a-z]*e")


if __name__ == "__main__":
    unittest.main(verbosity=2)
