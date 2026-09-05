#!/usr/bin/env python3
"""Tests for build.py's rendering helpers and freshness guards.

build.py is a script: importing it runs the guards, reads data/*.json and
overwrites public/digest.html. So its pure helpers are lifted out of the
source with ast rather than imported. See tests/helpers.py.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import load_from_source, source_of

B = load_from_source("build.py", [
    "E", "chg_class", "grid", "table", "sourced_para", "rate_cell", "_strip_md",
    "rotation_note", "blocked_outlets_note",
])


class Escaping(unittest.TestCase):
    """Every headline is third-party text, so escaping is a safety boundary."""

    def test_escapes_markup(self):
        self.assertEqual(B["E"]("<script>alert(1)</script>"),
                         "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_escapes_ampersands_and_quotes(self):
        out = B["E"]('AT&T "quoted"')
        self.assertIn("&amp;", out)
        self.assertIn("&quot;", out)

    def test_none_stringifies_rather_than_vanishing(self):
        """Documents the contract: a missing value shows as "None" on the page
        instead of silently disappearing, so the data bug stays visible."""
        self.assertEqual(B["E"](None), "None")

    def test_leaves_plain_text_alone(self):
        self.assertEqual(B["E"]("Plain text"), "Plain text")


class ChgClass(unittest.TestCase):
    def test_positive_and_negative_map_to_the_colour_tokens(self):
        self.assertEqual(B["chg_class"]("+1.50%"), "chg-pos")
        self.assertEqual(B["chg_class"]("-1.50%"), "chg-neg")

    def test_unicode_minus_is_treated_as_negative(self):
        self.assertEqual(B["chg_class"]("\u22121.50%"), "chg-neg")

    def test_flat_is_not_coloured_negative(self):
        self.assertNotEqual(B["chg_class"]("+0.00%"), "chg-neg")

    def test_empty_is_safe(self):
        self.assertIsInstance(B["chg_class"](""), str)


class SourcedPara(unittest.TestCase):
    def test_plain_text_when_there_is_no_source(self):
        for empty in ([], None):
            out = B["sourced_para"]("Some prose.", empty)
            self.assertEqual(out, "Some prose.")
            self.assertNotIn("<a", out)

    def test_appends_the_citation_as_a_link(self):
        out = B["sourced_para"]("Prose leading in:",
                                [{"title": "The headline",
                                  "url": "https://example.com/a"}])
        self.assertIn('<a href="https://example.com/a">The headline</a>', out)
        self.assertTrue(out.rstrip().endswith("."))

    def test_the_citation_is_escaped(self):
        out = B["sourced_para"]("Prose:", [{"title": "A & B <b>",
                                            "url": "https://x.com/?a=1&b=2"}])
        self.assertIn("&amp;", out)
        self.assertNotIn("<b>", out)

    def test_the_body_text_is_escaped(self):
        out = B["sourced_para"]("<script>", [])
        self.assertNotIn("<script>", out)

    def test_only_the_first_source_is_rendered(self):
        out = B["sourced_para"]("P:", [{"title": "One", "url": "u1"},
                                       {"title": "Two", "url": "u2"}])
        self.assertIn("One", out)
        self.assertNotIn("Two", out)


class Grid(unittest.TestCase):
    def test_wraps_cells_in_the_four_column_grid(self):
        out = B["grid"](["<div>a</div>", "<div>b</div>"])
        self.assertIn('class="rate-grid"', out)
        self.assertIn("<div>a</div>", out)

    def test_empty_input_still_produces_a_container(self):
        self.assertIn("rate-grid", B["grid"]([]))


class RateCell(unittest.TestCase):
    def cell(self, code="AUD", value="0.6543", chg="+0.21%",
             url="https://xe.com/aud", sub=None):
        return B["rate_cell"](code, value, chg, url, sub)

    def test_renders_code_value_and_link(self):
        out = self.cell()
        self.assertIn("AUD", out)
        self.assertIn("0.6543", out)
        self.assertIn('href="https://xe.com/aud"', out)

    def test_every_cell_is_a_link(self):
        """The hard rule: no data point appears as bare unlinked text."""
        self.assertIn("<a class=\"rate-cell\" href=", self.cell())

    def test_change_carries_a_colour_class(self):
        self.assertIn("chg-pos", self.cell())
        self.assertIn("chg-neg", self.cell(chg="-0.21%"))

    def test_a_sub_label_is_shown_when_given(self):
        self.assertIn("proxy", self.cell(sub="proxy"))
        self.assertIn("stale", self.cell(sub="stale"))

    def test_no_sub_label_adds_no_chip(self):
        self.assertNotIn("rc-sub", self.cell())

    def test_an_absent_change_renders_no_small_tag(self):
        """USD is the base rate and shows no percentage."""
        self.assertNotIn("<small", self.cell(chg=""))

    def test_content_is_escaped(self):
        self.assertNotIn("<img", self.cell(code="<img src=x>"))


class Table(unittest.TestCase):
    def rows(self, n=2):
        return [{"name": "Co %d" % i, "url": "https://x.com/%d" % i,
                 "price": "1.0%d" % i, "chg": "+1.0%d%%" % i, "vol": "1.2M"}
                for i in range(n)]

    def test_renders_the_four_column_header(self):
        out = B["table"]("Gainers", self.rows())
        for head in ("Gainers", "Price", "Chg", "Vol"):
            self.assertIn(head, out)

    def test_every_name_is_a_link(self):
        """The hard rule: no data point appears as bare unlinked text."""
        out = B["table"]("Gainers", self.rows(3))
        self.assertEqual(out.count("<a href="), 3)

    def test_gains_and_losses_are_coloured(self):
        out = B["table"]("Losers", [dict(self.rows(1)[0], chg="-4.00%")])
        self.assertIn("chg-neg", out)

    def test_empty_rows_do_not_crash(self):
        self.assertIsInstance(B["table"]("Gainers", []), str)

    def test_names_are_escaped(self):
        out = B["table"]("Gainers", [dict(self.rows(1)[0], name="A & <b>B</b>")])
        self.assertIn("&amp;", out)
        self.assertNotIn("<b>B</b>", out)


class StripMarkdown(unittest.TestCase):
    """_strip_md walks a decoded JSON tree in place, unwrapping **bold**
    wrappers on the text fields the page renders."""

    def test_unwraps_a_bold_headline(self):
        node = {"headline": "**Fed holds rates**"}
        B["_strip_md"](node)
        self.assertEqual(node["headline"], "Fed holds rates")

    def test_applies_to_detail_and_summary_too(self):
        node = {"detail": "**d**", "summary": "**s**"}
        B["_strip_md"](node)
        self.assertEqual((node["detail"], node["summary"]), ("d", "s"))

    def test_recurses_into_nested_lists_and_dicts(self):
        node = {"sections": [{"items": [{"headline": "**Deep**"}]}]}
        B["_strip_md"](node)
        self.assertEqual(node["sections"][0]["items"][0]["headline"], "Deep")

    def test_leaves_other_fields_untouched(self):
        node = {"url": "https://x.com/**a**", "headline": "**H**"}
        B["_strip_md"](node)
        self.assertEqual(node["url"], "https://x.com/**a**")

    def test_only_strips_a_fully_wrapped_string(self):
        node = {"headline": "Partly **bold** text"}
        B["_strip_md"](node)
        self.assertEqual(node["headline"], "Partly **bold** text")

    def test_plain_values_are_left_alone(self):
        node = {"headline": "Plain"}
        B["_strip_md"](node)
        self.assertEqual(node["headline"], "Plain")


class CapitalRaiseSummaryIsNeverBackfilled(unittest.TestCase):
    """A hardcoded backfill.json summary once permanently overrode the fresh
    per-run summary for anz/uk/rest, freezing the paragraph under those
    regions' headings forever and letting it drift out of sync with an
    since-emptied items list. _apply_dedup_rules must never read
    bf["summaries"] again."""

    def setUp(self):
        self.B = load_from_source(
            "build.py", ["_apply_dedup_rules", "_region", "_drop", "_extend"])

    def run_rules(self, cr, bf, dedup_rules):
        self.B["cr"] = cr
        self.B["bf"] = bf
        self.B["_apply_dedup_rules"](dedup_rules)

    def test_a_freshly_generated_summary_survives_dedup_rules(self):
        cr = {"regions": [{"key": "anz", "name": "ANZ",
                           "summary": "This run's fresh summary", "items": []}]}
        bf = {"summaries": {"anz": "Old hardcoded summary from a past edition"}}
        self.run_rules(cr, bf, {"capital_raises": {"anz": {}}})
        self.assertEqual(cr["regions"][0]["summary"], "This run's fresh summary")

    def test_the_source_no_longer_reads_a_backfilled_summary(self):
        src = source_of("build.py")
        self.assertNotIn('bf.get("summaries"', src)

    def test_the_shipped_backfill_file_carries_no_stale_summaries(self):
        """Guards against someone re-adding a permanent-override paragraph to
        data/backfill.json now that the code no longer reads it."""
        import json
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data", "backfill.json")
        with open(path) as f:
            bf = json.load(f)
        self.assertFalse(bf.get("summaries"))


class FreshnessGuardConfig(unittest.TestCase):
    """The guard is the reason a stale digest cannot be published silently."""

    def test_the_default_window_is_enforced_not_disabled(self):
        self.assertIn('MAX_DATA_AGE_HOURS", "36"', source_of("build.py"))

    def test_the_guard_exits_rather_than_warning(self):
        src = source_of("build.py")
        guard = src[src.index("def _check_freshness"):src.index("def _strip_md")]
        self.assertIn("sys.exit(1)", guard)

    def test_the_performers_guard_also_exits(self):
        src = source_of("build.py")
        guard = src[src.index("def _check_performers_fresh"):]
        self.assertIn("sys.exit(1)", guard[:guard.index("\ndef ")])

    def test_the_override_is_explicit(self):
        self.assertIn("MAX_DATA_AGE_HOURS=0", source_of("build.py"))

    def test_abc_us_and_guardian_are_covered_too(self):
        src = source_of("build.py")
        guard = src[src.index("def _check_freshness"):src.index("def _strip_md")]
        self.assertIn('"news-abcus.json"', guard)
        self.assertIn('"guardian.json"', guard)


class RotationNote(unittest.TestCase):
    """The footer's story-rotation claim must reflect this run's real
    fresh-vs-repeated counts, not a fixed statement about a prior run."""

    def _regions(self, fresh_counts, item_counts):
        return {"regions": [
            {"items": [0] * n, "fresh_count": f}
            for f, n in zip(fresh_counts, item_counts)
        ]}

    def test_no_previous_edition_is_stated_plainly(self):
        cr = self._regions([0], [3])
        eg = self._regions([0], [2])
        note = B["rotation_note"](cr, eg, False)
        self.assertIn("No previous local edition", note)

    def test_counts_reflect_the_actual_fresh_and_repeated_totals(self):
        cr = self._regions([2, 0], [3, 1])
        eg = self._regions([1], [1])
        note = B["rotation_note"](cr, eg, True)
        # total=5, fresh=3, repeated=2
        self.assertIn("5 Capital Raises and Market Earnings Reporting", note)
        self.assertIn("3 are newly sourced", note)
        self.assertIn("2 repeat", note)

    def test_zero_tracked_items_does_not_divide_by_zero(self):
        cr = self._regions([], [])
        eg = self._regions([], [])
        note = B["rotation_note"](cr, eg, True)
        self.assertIn("No rotation-tracked items", note)

    def test_no_hardcoded_prior_run_claim_remains(self):
        self.assertNotIn("sign-in wall", source_of("build.py"))
        self.assertNotIn("previously published artifact could not be "
                          "retrieved", source_of("build.py"))


class BlockedOutletsNote(unittest.TestCase):
    """The footer's blocked-outlet line must come from this run's live
    retry (fetch_news.py), not a fixed list assumed to still be accurate."""

    def test_none_blocked_says_so_plainly(self):
        note = B["blocked_outlets_note"]({"blocked": []}, "ABC and SBS")
        self.assertIn("responded successfully", note)

    def test_blocked_outlets_are_named_from_the_live_check(self):
        note = B["blocked_outlets_note"](
            {"blocked": ["news.com.au", "smh.com.au"]}, "ABC and SBS")
        self.assertIn("news.com.au, smh.com.au", note)
        self.assertIn("ABC and SBS", note)

    def test_config_no_longer_provides_a_fixed_outlet_list_to_the_footer(self):
        src = source_of("build.py")
        self.assertNotIn('cfg["footer"]["unavailable_outlets"]', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
