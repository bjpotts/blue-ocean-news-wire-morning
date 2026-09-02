#!/usr/bin/env python3
"""Tests for fetch_markets: FX/index formatting and the stale-data guards.

The guards matter more than the formatting. Yahoo still answers for IMOEX.ME
but its series froze in July 2022, so without a drop rule the page would
publish a four-year-old number as today's close.
"""
import contextlib
import io
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_markets as FM


class Fmt(unittest.TestCase):
    def test_large_values_lose_the_decimals(self):
        self.assertEqual(FM._fmt(53631.11), "53,631")
        self.assertEqual(FM._fmt(10000), "10,000")

    def test_mid_values_keep_two_decimals(self):
        self.assertEqual(FM._fmt(7683.14), "7,683.14")
        self.assertEqual(FM._fmt(1000), "1,000.00")

    def test_small_values_keep_four_decimals(self):
        self.assertEqual(FM._fmt(0.6543), "0.6543")
        self.assertEqual(FM._fmt(1.5), "1.5000")

    def test_none_is_blank_not_an_error(self):
        self.assertEqual(FM._fmt(None), "")

    def test_boundaries(self):
        self.assertEqual(FM._fmt(999.9999), "999.9999")   # below the 1000 cutover
        self.assertEqual(FM._fmt(9999.99), "9,999.99")
        self.assertEqual(FM._fmt(10000.4), "10,000")


class Pct(unittest.TestCase):
    def test_gain_is_signed_positive(self):
        self.assertEqual(FM._pct(100, 101), "+1.00%")

    def test_loss_is_signed_negative(self):
        self.assertEqual(FM._pct(100, 99), "-1.00%")

    def test_flat_is_zero(self):
        self.assertEqual(FM._pct(100, 100), "+0.00%")

    def test_missing_or_zero_previous_is_safe(self):
        """A divide-by-zero here would abort the whole markets fetch."""
        for prev, curr in ((0, 100), (None, 100), (100, None), (None, None)):
            self.assertEqual(FM._pct(prev, curr), "0.00%")

    def test_rounds_to_two_places(self):
        self.assertEqual(FM._pct(100, 100.5), "+0.50%")
        self.assertEqual(FM._pct(100, 101.234), "+1.23%")


class IndexStaleGuard(unittest.TestCase):
    """_stale_flag decides whether a quote is fresh, flagged or dropped."""

    def setUp(self):
        self.now = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)

    def flag(self, days_old):
        ts = datetime.now(FM.UTC) - timedelta(days=days_old)
        return self.quietly("Test Index", "^TEST", ts)[0]

    def quietly(self, *a):
        """_stale_flag reports its verdict on stderr; keep the suite clean."""
        with contextlib.redirect_stderr(io.StringIO()):
            return FM._stale_flag(*a)

    def test_todays_quote_is_kept(self):
        self.assertEqual(self.flag(0), "keep")

    def test_a_recent_quote_is_kept(self):
        self.assertEqual(self.flag(FM.STALE_AFTER_DAYS - 1), "keep")

    def test_an_older_quote_is_flagged(self):
        self.assertEqual(self.flag(FM.STALE_AFTER_DAYS + 1), "flag")

    def test_a_long_dead_series_is_dropped(self):
        """The MOEX case: Yahoo answers, but the series stopped in 2022."""
        self.assertEqual(self.flag(FM.DROP_AFTER_DAYS + 1), "drop")
        self.assertEqual(self.flag(365 * 4), "drop")

    def test_thresholds_are_ordered_sensibly(self):
        self.assertLess(FM.STALE_AFTER_DAYS, FM.DROP_AFTER_DAYS)

    def test_missing_timestamp_is_kept_with_no_age(self):
        self.assertEqual(self.quietly("n", "s", None), ("keep", None))

    def test_age_is_reported_alongside_the_verdict(self):
        _verdict, age = self.quietly(
            "n", "s", datetime.now(FM.UTC) - timedelta(days=9))
        self.assertEqual(age, 9)


class IndexConfig(unittest.TestCase):
    def test_the_grid_is_the_expected_size(self):
        """The grid is 4 columns; a lone 9th cell trails the second full row."""
        self.assertEqual(len(FM.INDICES), 9)

    def test_index_symbols_are_unique(self):
        syms = [s for _n, s in FM.INDICES]
        self.assertEqual(len(syms), len(set(syms)))

    def test_index_names_are_unique(self):
        names = [n for n, _s in FM.INDICES]
        self.assertEqual(len(names), len(set(names)))

    def test_the_required_regions_are_all_represented(self):
        names = " ".join(n for n, _s in FM.INDICES)
        for expected in ("Dow Jones", "S&P 500", "Nasdaq Composite",
                         "Russell 2000", "S&P/ASX 200", "All Ordinaries",
                         "FTSE 100", "FTSE 250", "FTSE 350"):
            self.assertIn(expected, names)


class NarrativeIndexConfig(unittest.TestCase):
    """Dropped from the 9-cell grid but still fetched so the hand-written
    Market News paragraph can keep citing them - see the mega-prompt's
    "genuinely broad world coverage" requirement."""

    def test_no_overlap_with_the_visible_grid(self):
        grid_syms = {s for _n, s in FM.INDICES}
        narrative_syms = {s for _n, s in FM.NARRATIVE_INDICES}
        self.assertEqual(grid_syms & narrative_syms, set())

    def test_the_required_narrative_regions_are_covered(self):
        names = " ".join(n for n, _s in FM.NARRATIVE_INDICES)
        for expected in ("DAX", "CAC 40", "Hang Seng", "Nikkei 225", "KOSPI",
                         "Shanghai Composite", "Ibovespa", "Straits Times",
                         "BSE Sensex"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
