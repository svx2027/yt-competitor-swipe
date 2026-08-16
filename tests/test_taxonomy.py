"""Tests for the topic taxonomy: rule-based title tagging, specificity/tie-
break order, and the session-label merge for rule leftovers.

Pure-function tests against a small fictional taxonomy fixture - no network
calls, no dependency on config/taxonomy.yml (that file is ported per-vertical,
separately from this engine code). Run from the repo root:

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from src import taxonomy


TAXONOMY = [
    {"label": "strength-training-gear", "hints": ["kettlebell", "dumbbell", "rack"]},
    {"label": "buying-guides", "hints": ["buying guide", "budget"]},
    {"label": "recovery-and-mobility", "hints": ["mobility", "recovery"]},
    {"label": "misc", "hints": []},
]


class TagTitleTests(unittest.TestCase):
    def test_matches_longest_hint(self):
        # "buying guide" (13 chars) beats "budget" (6 chars) even though both
        # substring-match the title.
        label = taxonomy.tag_title("The Budget Kettlebell Buying Guide", TAXONOMY)
        self.assertEqual(label, "buying-guides")

    def test_single_hint_match(self):
        label = taxonomy.tag_title("Best Adjustable Rack for Small Garages", TAXONOMY)
        self.assertEqual(label, "strength-training-gear")

    def test_no_match_returns_empty(self):
        label = taxonomy.tag_title("Our Studio Tour", TAXONOMY)
        self.assertEqual(label, "")

    def test_tie_breaks_by_taxonomy_order_not_alphabetical(self):
        # Two equal-length hints from different labels ("rack" / "budget",
        # both len 4... use two genuinely equal-length hints across labels).
        tax = [
            {"label": "later-label", "hints": ["gear"]},
            {"label": "earlier-label", "hints": ["gear"]},
        ]
        # "earlier-label" is declared second but is NOT earlier in this list,
        # so the FIRST entry (index 0) should win on a tie.
        label = taxonomy.tag_title("Best Gear For Beginners", tax)
        self.assertEqual(label, "later-label")

    def test_case_insensitive(self):
        label = taxonomy.tag_title("KETTLEBELL Deals This Week", TAXONOMY)
        self.assertEqual(label, "strength-training-gear")

    def test_empty_title(self):
        self.assertEqual(taxonomy.tag_title("", TAXONOMY), "")
        self.assertEqual(taxonomy.tag_title(None, TAXONOMY), "")


class ValidLabelsTests(unittest.TestCase):
    def test_collects_all_labels(self):
        self.assertEqual(taxonomy.valid_labels(TAXONOMY),
                         {"strength-training-gear", "buying-guides",
                          "recovery-and-mobility", "misc"})


class LoadSessionLabelsTests(unittest.TestCase):
    def test_drops_invalid_labels(self):
        with patch.object(taxonomy.common, "read_json",
                          return_value={"vid1": "misc", "vid2": "not-a-real-label"}):
            out = taxonomy.load_session_labels(TAXONOMY)
        self.assertEqual(out, {"vid1": "misc"})

    def test_missing_cache_returns_empty(self):
        with patch.object(taxonomy.common, "read_json", return_value={}):
            self.assertEqual(taxonomy.load_session_labels(TAXONOMY), {})


class TagCandidateTests(unittest.TestCase):
    def test_rule_wins_over_session_label(self):
        c = {"video_id": "v1", "title": "Kettlebell Roundup"}
        out = taxonomy.tag_candidate(c, TAXONOMY, {"v1": "misc"})
        self.assertEqual(out, "strength-training-gear")

    def test_falls_back_to_session_label_when_no_rule_matches(self):
        c = {"video_id": "v1", "title": "Our Studio Tour"}
        out = taxonomy.tag_candidate(c, TAXONOMY, {"v1": "misc"})
        self.assertEqual(out, "misc")

    def test_no_rule_no_session_label_stays_pending(self):
        c = {"video_id": "v1", "title": "Our Studio Tour"}
        out = taxonomy.tag_candidate(c, TAXONOMY, {})
        self.assertEqual(out, "")

    def test_keys_on_post_url_when_no_video_id(self):
        c = {"post_url": "https://example.com/p1", "title": "Our Studio Tour"}
        out = taxonomy.tag_candidate(c, TAXONOMY, {"https://example.com/p1": "misc"})
        self.assertEqual(out, "misc")


if __name__ == "__main__":
    unittest.main()
