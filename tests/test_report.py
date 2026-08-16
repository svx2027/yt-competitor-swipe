"""Tests for the report generator's pure formatting and fallback-narrative
functions: number/duration formatting, the deterministic "make this call" /
"why" / "strategist take" fallbacks, and section rendering.

Fictional home-fitness-gear-review fixtures, matching tests/test_scoring.py -
no network calls, no dependency on config.yaml (a minimal fixture cfg is
built here so this test suite does not break if the shipped demo config
changes). Run from the repo root:

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from src import report


def _cfg():
    return {
        "report": {
            "section_min": 2,
            "section_max": 3,
            "take_label": "Strategist take",
            "self_channel_eng_name": "HomeRack Fitness EN",
            "self_channel_fallback_name": "main HomeRack Fitness channel",
            "section_routing": [
                {"label": "Strength Gear", "hints": ["kettlebell", "rack"]},
                {"label": "Cardio & Recovery", "hints": ["cardio", "mobility"]},
            ],
            "calendar_cycle_label": "seasonal-fitness-demand cycle",
        },
    }


class FormatTests(unittest.TestCase):
    def test_fmt_int(self):
        self.assertEqual(report.fmt_int(1234567), "1,234,567")
        self.assertEqual(report.fmt_int("bad"), "bad")

    def test_fmt_subs(self):
        self.assertEqual(report.fmt_subs(1_500_000), "1.5M")
        self.assertEqual(report.fmt_subs(52_000), "52K")
        self.assertEqual(report.fmt_subs(340), "340")
        self.assertEqual(report.fmt_subs(0), "n/a")

    def test_fmt_hours(self):
        self.assertEqual(report.fmt_hours(None), "?")
        self.assertEqual(report.fmt_hours(0.5), "30m ago")
        self.assertEqual(report.fmt_hours(5.0), "5.0h ago")
        self.assertEqual(report.fmt_hours(72.0), "3.0d ago")

    def test_channel_line(self):
        c = {"channel_name": "GearHead Fitness Lab", "relation": "direct",
             "channel_type": "channel", "channel_subs": 412000}
        self.assertEqual(report.channel_line(c),
                         "GearHead Fitness Lab (direct, channel, 412K subs)")


class MakeThisCallTests(unittest.TestCase):
    """Flag priority order matters: BREAKOUT beats CONVERGENCE beats
    DEMAND_GAP beats HOT_ENGAGEMENT beats CALENDAR beats the plain fallback."""

    def test_breakout_takes_priority(self):
        c = {"format": "short", "flags": ["BREAKOUT", "CONVERGENCE", "CALENDAR"]}
        out = report.make_this_call(c, _cfg())
        self.assertIn("over-indexing", out)
        self.assertTrue(out.startswith("Remix as a Short"))

    def test_convergence_beats_demand_gap(self):
        c = {"format": "longform", "flags": ["DEMAND_GAP", "CONVERGENCE"]}
        out = report.make_this_call(c, _cfg())
        self.assertIn("piling onto this hook", out)

    def test_calendar_uses_configured_label(self):
        c = {"format": "livestream", "flags": ["CALENDAR"]}
        out = report.make_this_call(c, _cfg())
        self.assertIn("seasonal-fitness-demand cycle", out)

    def test_no_flags_falls_back_to_vph(self):
        c = {"format": "post", "flags": []}
        out = report.make_this_call(c, _cfg())
        self.assertIn("strong views-per-hour", out)
        self.assertTrue(out.startswith("Echo as a community post:"))

    def test_unknown_format_falls_back_to_generic_verb(self):
        c = {"format": "unknown-format", "flags": []}
        out = report.make_this_call(c, _cfg())
        self.assertTrue(out.startswith("Remix:"))


class FallbackWhyTests(unittest.TestCase):
    def test_assembles_qualifying_bits_only(self):
        c = {"vph": 2750, "outlier": 1.0, "comment_vph_z": 0.2,
             "convergence_size": 0, "calendar_boost": 0, "_components": {"vph": 80}}
        out = report.fallback_why(c)
        self.assertIn("VPH 2,750", out)
        self.assertNotIn("channel's own expected pace", out)  # outlier < 1.5

    def test_empty_candidate_gets_default_line(self):
        self.assertEqual(report.fallback_why({}), "Ranks on views-per-hour within today's set.")

    def test_convergence_bit_included_above_threshold(self):
        c = {"convergence_size": 3, "cluster_label": "budget / kettlebell"}
        out = report.fallback_why(c)
        self.assertIn("3 competitors hitting 'budget / kettlebell'", out)


class FallbackStrategistTakeTests(unittest.TestCase):
    def test_routes_to_matching_section(self):
        c = {"format": "longform", "lang": "eng", "relation": "direct",
             "cluster_label": "budget / kettlebell"}
        out = report.fallback_strategist_take(c, _cfg())
        self.assertIn("HomeRack Fitness EN", out)
        self.assertIn("Route to Strength Gear.", out)
        self.assertIn("direct head-to-head", out)

    def test_indirect_relation_uses_benchmark_framing(self):
        c = {"format": "short", "lang": "eng", "relation": "indirect", "cluster_label": ""}
        out = report.fallback_strategist_take(c, _cfg())
        self.assertIn("benchmark idea, not the lesson", out)

    def test_non_english_uses_fallback_channel_name(self):
        c = {"format": "post", "lang": "mix", "relation": "direct", "cluster_label": ""}
        out = report.fallback_strategist_take(c, _cfg())
        self.assertIn("main HomeRack Fitness channel", out)

    def test_no_cluster_match_omits_routing_sentence(self):
        c = {"format": "longform", "lang": "eng", "relation": "direct", "cluster_label": "misc topic"}
        out = report.fallback_strategist_take(c, _cfg())
        self.assertNotIn("Route to", out)


class EnrichTests(unittest.TestCase):
    def test_narrative_override_wins_over_fallback(self):
        c = {"video_id": "v1", "vph": 100, "flags": []}
        narratives = {"v1": {"why": "Session-authored reason.",
                             "strategist_take": "Session-authored take."}}
        report.enrich(c, narratives, _cfg())
        self.assertEqual(c["why"], "Session-authored reason.")
        self.assertEqual(c["strategist_take"], "Session-authored take.")

    def test_falls_back_when_no_narrative(self):
        c = {"video_id": "v1", "vph": 100, "flags": [], "format": "short",
             "lang": "eng", "relation": "direct", "cluster_label": ""}
        report.enrich(c, {}, _cfg())
        self.assertTrue(c["why"])
        self.assertTrue(c["strategist_take"])
        self.assertNotIn("Session-authored", c["strategist_take"])


class SectionTests(unittest.TestCase):
    def test_thin_field_note_below_section_min(self):
        cfg = _cfg()
        items = [{"format": "short", "kind": "video", "title": "Only one", "flags": [],
                 "channel_name": "X", "relation": "direct", "channel_type": "channel",
                 "channel_subs": 0, "why": "", "strategist_take": ""}]
        out = report._section("SECTION B", items, cfg)
        self.assertIn("only 1 qualified", out)

    def test_empty_section_shows_none(self):
        out = report._section("SECTION C", [], _cfg())
        self.assertIn("(none this run)", out)


if __name__ == "__main__":
    unittest.main()
