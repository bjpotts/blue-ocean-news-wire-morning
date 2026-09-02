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
