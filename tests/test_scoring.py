"""Tests for the scoring engine: VPH z-scores, the outlier multiplier,
title clustering, calendar boost, and the demand-gap signal.

Pure-function tests against fictional fixtures (a home-fitness-gear review
channel) - no network calls, no real channel data, and no dependency on
config/inputs files (those are ported per-vertical, separately from this
engine code). Run from the repo root:

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from src import common, keyword_demand, score


def _video(video_id, channel_id, title, vph=10.0, comment_vph=0.5,
           like_vph=1.0, eng_rate=0.05, hours_since=12.0, relation="direct",
           flags=None):
    return {
        "kind": "video", "video_id": video_id, "channel_id": channel_id,
        "channel_name": channel_id, "title": title, "vph": vph,
        "comment_vph": comment_vph, "like_vph": like_vph, "eng_rate": eng_rate,
        "hours_since": hours_since, "relation": relation,
        "flags": list(flags or []), "format": "longform",
    }


def _post(post_url, channel_id, title, likes=10.0, post_type="text",
          relation="direct", flags=None):
    return {
        "kind": "post", "post_url": post_url, "channel_id": channel_id,
        "channel_name": channel_id, "title": title, "likes": likes,
        "post_type": post_type, "relation": relation, "flags": list(flags or []),
    }


class ZScoreTests(unittest.TestCase):
    def test_zero_std_returns_all_zero(self):
        self.assertEqual(common.zscores([5.0, 5.0, 5.0]), [0.0, 0.0, 0.0])

    def test_normal_distribution_centers_on_mean(self):
        z = common.zscores([1.0, 2.0, 3.0])
        self.assertAlmostEqual(z[1], 0.0, places=6)
        self.assertGreater(z[2], z[0])

    def test_empty_input(self):
        self.assertEqual(common.zscores([]), [])


class ClampTests(unittest.TestCase):
    def test_clamps_both_directions(self):
        self.assertEqual(common.clamp(150, 0, 100), 100)
        self.assertEqual(common.clamp(-10, 0, 100), 0)
        self.assertEqual(common.clamp(50, 0, 100), 50)


class PctRankTests(unittest.TestCase):
    def test_empty_list_is_zero(self):
        self.assertEqual(score._pct_rank(10, []), 0.0)

    def test_highest_value_ranks_near_top(self):
        vals = sorted([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(score._pct_rank(5.0, vals), 80.0)  # 4 of 5 are below
        self.assertEqual(score._pct_rank(1.0, vals), 0.0)   # nothing below the min


class ClusteringTests(unittest.TestCase):
    def test_ubiquitous_token_dropped_unless_anchor(self):
        videos = [
            {"title": "Kettlebell Circuit for Beginners"},
            {"title": "Kettlebell Complex for Strength"},
            {"title": "Yoga Flow for Mornings"},
        ]
        # "kettlebell" appears in 2/3 titles (above the 0.4 max_df threshold) -
        # dropped unless explicitly kept as a domain anchor.
        sets_dropped = score._filtered_token_sets(videos, keep=set(), max_df=0.4)
        self.assertNotIn("kettlebell", sets_dropped[0])
        sets_kept = score._filtered_token_sets(videos, keep={"kettlebell"}, max_df=0.4)
        self.assertIn("kettlebell", sets_kept[0])

    def test_local_clusters_avoid_mega_cluster(self):
        # Two clearly distinct subtopics sharing a bridge word ("home"/"setup")
        # must NOT collapse into one cluster via transitive chaining - each
        # title anchors on its own rarest token instead.
        videos = [
            {"title": "Home Gym Budget Setup"},
            {"title": "Home Gym Flooring Guide"},
            {"title": "Home Office Desk Setup"},
        ]
        token_sets = score._filtered_token_sets(videos, keep=set(), max_df=1.0)
        clusters = score._local_clusters(token_sets)
        sizes = sorted(len(c) for c in clusters)
        self.assertEqual(sum(sizes), 3)
        self.assertLess(max(sizes), 3)


class OutlierTests(unittest.TestCase):
    def test_same_run_median_fallback(self):
        # No vidIQ/baseline cache on disk in a fresh checkout, so this exercises
        # the weakest ("same-run") path: outlier = vph / the channel's own
        # median vph within this run.
        videos = [
            _video("v1", "chan_a", "Video A", vph=10.0),
            _video("v2", "chan_a", "Video B", vph=20.0),
            _video("v3", "chan_a", "Video C", vph=40.0),
        ]
        score.compute_outliers(videos, cfg={})
        for v in videos:
            self.assertEqual(v["outlier_source"], "same-run")
        self.assertEqual(videos[0]["outlier"], 0.5)
        self.assertEqual(videos[1]["outlier"], 1.0)
        self.assertEqual(videos[2]["outlier"], 2.0)

    def test_extreme_ratio_capped_at_20x(self):
        videos = [
            _video("v1", "chan_b", "Video A", vph=1.0),
            _video("v2", "chan_b", "Video B", vph=1.0),
            _video("v3", "chan_b", "Video C", vph=500.0),
        ]
        score.compute_outliers(videos, cfg={})
        self.assertEqual(videos[2]["outlier"], 20.0)

    def test_zero_vph_channel_defaults_to_1x(self):
        videos = [_video("v1", "chan_c", "Video A", vph=0.0)]
        score.compute_outliers(videos, cfg={})
        self.assertEqual(videos[0]["outlier"], 1.0)


class CalendarTests(unittest.TestCase):
    def _calendar(self):
        today = common.today_ist_date()
        return {"phases": [{
            "key": "launch-week", "label": "Launch week",
            "start": today, "end": today,
            "boost_hooks": ["new gear drop", "unboxing"],
        }]}

    def test_matching_hook_sets_calendar_flag(self):
        videos = [_video("v1", "chan_a", "New Gear Drop: First Look")]
        phase = score.apply_calendar(videos, self._calendar())
        self.assertEqual(phase["key"], "launch-week")
        self.assertIn("CALENDAR", videos[0]["flags"])
        self.assertGreaterEqual(videos[0]["calendar_boost"], 0.5)

    def test_no_active_phase_leaves_videos_unboosted(self):
        videos = [_video("v1", "chan_a", "Unrelated Title")]
        phase = score.apply_calendar(videos, {"phases": []})
        self.assertIsNone(phase)
        self.assertIsNone(videos[0]["calendar_phase"])
        self.assertEqual(videos[0]["calendar_boost"], 0.0)


class DemandGapTests(unittest.TestCase):
    def _candidates(self):
        return [_video("v1", "chan_a", "Best Budget Kettlebell Set Review")]

    def test_no_vidiq_cache_never_flags_demand_gap(self):
        # Degraded mode (no vidIQ cache on disk): alignment is a computed
        # fallback score, and DEMAND_GAP requires real vidIQ metrics, so it
        # must never fire from the fallback alone.
        candidates = self._candidates()
        cfg = {"flags": {"demand_gap_min_score": 60}}
        with patch.object(common, "load_keywords", return_value=["budget kettlebell set"]):
            keyword_demand.annotate_candidates(candidates, cfg)
        self.assertNotIn("DEMAND_GAP", candidates[0]["flags"])
        self.assertGreater(candidates[0]["demand_gap_score"], 0)

    def test_strong_underserved_keyword_flags_demand_gap(self):
        candidates = self._candidates()
        cfg = {"flags": {"demand_gap_min_score": 60}}
        vidiq_metrics = {
            "budget kettlebell set": {"overall_score": 75, "competition": 20, "volume": 40},
        }
        with patch.object(common, "load_keywords", return_value=["budget kettlebell set"]), \
             patch.object(keyword_demand, "load_vidiq_keywords", return_value=vidiq_metrics):
            keyword_demand.annotate_candidates(candidates, cfg)
        self.assertIn("DEMAND_GAP", candidates[0]["flags"])
        self.assertEqual(candidates[0]["demand_gap_score"], 75.0)

    def test_strong_keyword_but_high_competition_does_not_flag(self):
        candidates = self._candidates()
        cfg = {"flags": {"demand_gap_min_score": 60}}
        vidiq_metrics = {
            "budget kettlebell set": {"overall_score": 90, "competition": 80, "volume": 40},
        }
        with patch.object(common, "load_keywords", return_value=["budget kettlebell set"]), \
             patch.object(keyword_demand, "load_vidiq_keywords", return_value=vidiq_metrics):
            keyword_demand.annotate_candidates(candidates, cfg)
        self.assertNotIn("DEMAND_GAP", candidates[0]["flags"])

    def test_best_keyword_match_requires_two_token_overlap(self):
        # A single shared common word must never match alone.
        kw, score_val = keyword_demand.best_keyword_match(
            "Morning Routine Vlog", kw_metrics={}, universe=["vlog tips"])
        self.assertEqual(kw, "")
        self.assertEqual(score_val, 0.0)

    def test_zero_hours_since_counts_as_fresh_not_stale(self):
        # Regression: a video published within the current hour (hours_since
        # == 0) must register as fresh supply, not fall through a falsy-zero
        # bug that treats 0 the same as "unknown".
        candidates = [_video("v1", "chan_a", "Budget Kettlebell Set Deal", hours_since=0.0)]
        cfg = {"flags": {"demand_gap_min_score": 60}}
        vidiq_metrics = {"budget kettlebell set": {"overall_score": 80, "competition": 50, "volume": 60}}
        with patch.object(common, "load_keywords", return_value=list(vidiq_metrics.keys())), \
             patch.object(keyword_demand, "load_vidiq_keywords", return_value=vidiq_metrics):
            rows = keyword_demand.build_demand_section(candidates, cfg)
        row = rows[0]
        self.assertEqual(row["supply_newest_hours"], 0.0)
        self.assertFalse(row["stale_or_thin"])


class SingleTokenKeywordTests(unittest.TestCase):
    """Regression coverage: a one-word keyword can contribute at most one
    overlapping token, so it must not be held to the same >=2 threshold used
    for multi-word keywords."""

    def test_single_token_keyword_can_be_the_best_match(self):
        kw, score_val = keyword_demand.best_keyword_match(
            "Kettlebell Basics for Beginners",
            kw_metrics={"kettlebell": {"overall_score": 55}}, universe=[])
        self.assertEqual(kw, "kettlebell")
        self.assertEqual(score_val, 55.0)

    def test_single_token_keyword_counts_as_supply(self):
        candidates = [_video("v1", "chan_a", "Kettlebell Basics for Beginners")]
        supply = keyword_demand._supply_for_keyword("kettlebell", candidates)
        self.assertEqual(supply["matches"], 1)


class BuildDemandSectionTests(unittest.TestCase):
    def test_ranks_thin_supply_above_well_served_query(self):
        candidates = [
            _video("v1", "chan_a", "Best Budget Kettlebell Set Review", hours_since=5.0),
            _video("v2", "chan_b", "Best Budget Kettlebell Set Guide", hours_since=6.0),
        ]
        cfg = {"flags": {"demand_gap_min_score": 60}}
        vidiq_metrics = {
            "budget kettlebell set": {"overall_score": 80, "competition": 50, "volume": 60},
            "yoga flow routine": {"overall_score": 70, "competition": 55, "volume": 45},
        }
        with patch.object(common, "load_keywords", return_value=list(vidiq_metrics.keys())), \
             patch.object(keyword_demand, "load_vidiq_keywords", return_value=vidiq_metrics):
            rows = keyword_demand.build_demand_section(candidates, cfg)
        by_kw = {r["keyword"]: r for r in rows}
        # "budget kettlebell set" is well-served by two fresh candidate videos;
        # "yoga flow routine" has zero supply, so it must show a strictly
        # higher gap score and the stale_or_thin flag.
        self.assertTrue(by_kw["yoga flow routine"]["stale_or_thin"])
        self.assertGreater(by_kw["yoga flow routine"]["gap_score"], by_kw["budget kettlebell set"]["gap_score"])
        self.assertEqual(rows[0]["keyword"], "yoga flow routine")  # sorted by gap score, highest first


class HistorySignalTests(unittest.TestCase):
    """apply_history_signals: SLEEPER (VPH re-acceleration) and NEW_FORMAT
    (a channel's first upload in a format it hasn't used before, once there
    is enough history to judge that)."""

    def _cfg(self):
        return {
            "output": {"history_csv": "data/history.csv"},
            "sleeper": {"min_age_hours": 48, "min_vph_growth_pct": 20},
            "flags": {"new_format_min_history_rows": 3},
        }

    def test_sleeper_flag_on_reaccelerating_video(self):
        hist = [{"video_or_post_id": "v1", "vph": "10", "channel": "chan_a", "format": "longform"}]
        videos = [_video("v1", "chan_a", "Re-accelerating Video", vph=15.0, hours_since=72.0)]
        with patch.object(common, "read_history", return_value=hist):
            score.apply_history_signals(videos, self._cfg())
        self.assertIn("SLEEPER", videos[0]["flags"])
        self.assertEqual(videos[0]["sleeper_prev_vph"], 10.0)

    def test_too_young_video_never_flagged_sleeper(self):
        hist = [{"video_or_post_id": "v1", "vph": "10", "channel": "chan_a", "format": "longform"}]
        videos = [_video("v1", "chan_a", "Fresh Video", vph=15.0, hours_since=1.0)]
        with patch.object(common, "read_history", return_value=hist):
            score.apply_history_signals(videos, self._cfg())
        self.assertNotIn("SLEEPER", videos[0]["flags"])

    def test_new_format_flag_requires_enough_history(self):
        hist = [{"video_or_post_id": f"h{i}", "vph": "1", "channel": "chan_a", "format": "longform"}
                for i in range(3)]
        videos = [_video("v-short", "chan_a", "First Short Ever", vph=5.0, hours_since=10.0)]
        videos[0]["format"] = "short"
        with patch.object(common, "read_history", return_value=hist):
            score.apply_history_signals(videos, self._cfg())
        self.assertIn("NEW_FORMAT", videos[0]["flags"])

    def test_new_format_flag_withheld_on_thin_history(self):
        hist = [{"video_or_post_id": "h0", "vph": "1", "channel": "chan_a", "format": "longform"}]
        videos = [_video("v-short", "chan_a", "First Short Ever", vph=5.0, hours_since=10.0)]
        videos[0]["format"] = "short"
        with patch.object(common, "read_history", return_value=hist):
            score.apply_history_signals(videos, self._cfg())
        self.assertNotIn("NEW_FORMAT", videos[0]["flags"])


def _minimal_score_cfg(**overrides):
    cfg = {
        "weights": {"vph": 40, "outlier": 20, "engagement": 15, "demand_gap": 10,
                    "convergence": 10, "calendar": 5},
        "relation_weights": {"direct": 1.0, "indirect": 0.85, "self": 0.0},
        "engagement_subweights": {"comment_vph_z": 0.55, "like_vph_z": 0.25, "eng_rate_z": 0.20},
        "niche": {"cluster_anchor_tokens": []},
        "convergence": {"min_cluster_size": 2, "window_hours": 48, "cluster_max_df": 0.4},
        "flags": {"breakout_outlier_min": 2.0, "hot_engagement_z_min": 1.5,
                  "demand_gap_min_score": 60, "new_format_min_history_rows": 8},
        "sleeper": {"min_age_hours": 48, "min_vph_growth_pct": 20},
        "output": {"history_csv": "data/history.csv"},
        "gemini": {"enabled": False},
    }
    cfg.update(overrides)
    return cfg


class ScoreAllIntegrationTests(unittest.TestCase):
    """End-to-end coverage of the blended Opportunity Score entry point -
    every component (z-scores, outlier, demand gap, convergence, calendar)
    feeds into this, so it needs its own test beyond the unit tests above."""

    def test_produces_ranked_opportunity_scores(self):
        candidates = [
            _video("v1", "chan_a", "Kettlebell Complex Circuit", vph=50.0, comment_vph=2.0,
                   like_vph=5.0, eng_rate=0.08, hours_since=6.0, relation="direct"),
            _video("v2", "chan_b", "Home Gym Flooring Guide", vph=45.0, comment_vph=1.8,
                   like_vph=4.5, eng_rate=0.07, hours_since=8.0, relation="direct"),
            _video("v3", "chan_c", "Yoga Flow for Mornings", vph=5.0, comment_vph=0.1,
                   like_vph=0.2, eng_rate=0.01, hours_since=30.0, relation="indirect"),
        ]
        cfg = _minimal_score_cfg()
        with patch.object(common, "load_keywords", return_value=[]), \
             patch.object(common, "read_history", return_value=[]):
            ranked, meta = score.score_all(candidates, cfg, calendar={"phases": []})
        self.assertEqual(meta["n_videos"], 3)
        self.assertEqual(ranked[0]["video_id"], "v1")  # highest vph and engagement
        for v in ranked:
            self.assertIn("opportunity_score", v)
            self.assertIn("_components", v)

    def test_convergence_counts_a_video_published_this_hour(self):
        # Regression: hours_since == 0 (published within the current hour)
        # must still count toward the convergence recency window, not be
        # silently dropped by a falsy-zero bug.
        candidates = [
            _video("v1", "chan_a", "Best New Kettlebell", vph=20.0, hours_since=0.0, relation="direct"),
            _video("v2", "chan_b", "Full Kettlebell Video", vph=18.0, hours_since=10.0, relation="direct"),
        ]
        cfg = _minimal_score_cfg(convergence={"min_cluster_size": 2, "window_hours": 48, "cluster_max_df": 1.0})
        with patch.object(common, "load_keywords", return_value=[]), \
             patch.object(common, "read_history", return_value=[]):
            ranked, _ = score.score_all(candidates, cfg, calendar={"phases": []})
        by_id = {v["video_id"]: v for v in ranked}
        self.assertEqual(by_id["v1"]["convergence_size"], 2)
        self.assertIn("CONVERGENCE", by_id["v1"]["flags"])

    def test_breakout_and_hot_engagement_flags_fire(self):
        candidates = [
            _video("v1", "chan_out", "Kettlebell Baseline One", vph=5.0, comment_vph=0.1, hours_since=20.0),
            _video("v2", "chan_out", "Kettlebell Baseline Two", vph=5.0, comment_vph=0.1, hours_since=22.0),
            _video("v3", "chan_out", "Kettlebell Baseline Three", vph=5.0, comment_vph=0.1, hours_since=24.0),
            _video("v4", "chan_out", "Kettlebell Viral Spike", vph=50.0, comment_vph=20.0, hours_since=3.0),
        ]
        cfg = _minimal_score_cfg()
        with patch.object(common, "load_keywords", return_value=[]), \
             patch.object(common, "read_history", return_value=[]):
            ranked, _ = score.score_all(candidates, cfg, calendar={"phases": []})
        spike = next(v for v in ranked if v["video_id"] == "v4")
        self.assertGreaterEqual(spike["outlier"], cfg["flags"]["breakout_outlier_min"])
        self.assertIn("BREAKOUT", spike["flags"])
        self.assertIn("HOT_ENGAGEMENT", spike["flags"])


class PostsScoringTests(unittest.TestCase):
    """The lighter-weight community-post scoring path (_score_posts), which
    score_all also feeds the blended ranking from."""

    def test_poll_post_scores_and_flags_hot_engagement(self):
        candidates = [
            _post("p1", "chan_a", "Which topic next?", likes=5.0, post_type="poll"),
            _post("p2", "chan_a", "Behind the scenes", likes=50.0, post_type="text"),
        ]
        cfg = _minimal_score_cfg()
        with patch.object(common, "load_keywords", return_value=[]), \
             patch.object(common, "read_history", return_value=[]):
            ranked, meta = score.score_all(candidates, cfg, calendar={"phases": []})
        self.assertEqual(meta["n_posts"], 2)
        poll = next(p for p in ranked if p["post_url"] == "p1")
        self.assertIn("HOT_ENGAGEMENT", poll["flags"])
        self.assertIn("opportunity_score", poll)

    def test_post_calendar_hook_sets_calendar_flag(self):
        today = common.today_ist_date()
        calendar = {"phases": [{
            "key": "launch-week", "label": "Launch week",
            "start": today, "end": today,
            "boost_hooks": ["new gear drop"],
        }]}
        candidates = [_post("p1", "chan_a", "New Gear Drop Announcement", likes=5.0, post_type="text")]
        cfg = _minimal_score_cfg()
        with patch.object(common, "load_keywords", return_value=[]), \
             patch.object(common, "read_history", return_value=[]):
            ranked, _ = score.score_all(candidates, cfg, calendar=calendar)
        self.assertIn("CALENDAR", ranked[0]["flags"])


class ZeroCompetitionDemandGapTests(unittest.TestCase):
    """Regression: a vidIQ competition score of exactly 0 (the ideal,
    most-underserved case) must not be coerced to the "unknown" fallback by
    a falsy-zero check - that would make DEMAND_GAP unable to ever fire for
    the single best case it exists to catch."""

    def test_zero_competition_still_flags_demand_gap(self):
        candidates = [_video("v1", "chan_a", "Best Budget Kettlebell Set Review")]
        cfg = {"flags": {"demand_gap_min_score": 60}}
        vidiq_metrics = {
            "budget kettlebell set": {"overall_score": 90, "competition": 0, "volume": 40},
        }
        with patch.object(common, "load_keywords", return_value=["budget kettlebell set"]), \
             patch.object(keyword_demand, "load_vidiq_keywords", return_value=vidiq_metrics):
            keyword_demand.annotate_candidates(candidates, cfg)
        self.assertIn("DEMAND_GAP", candidates[0]["flags"])

    def test_zero_competition_gets_the_gap_bonus_in_section_e(self):
        candidates = [_video("v1", "chan_a", "Best Budget Kettlebell Set Review", hours_since=5.0)]
        cfg = {"flags": {"demand_gap_min_score": 60}}
        vidiq_metrics = {
            "budget kettlebell set": {"overall_score": 50, "competition": 0, "volume": 40},
        }
        with patch.object(common, "load_keywords", return_value=["budget kettlebell set"]), \
             patch.object(keyword_demand, "load_vidiq_keywords", return_value=vidiq_metrics):
            rows = keyword_demand.build_demand_section(candidates, cfg)
        self.assertEqual(rows[0]["competition"], 0.0)
        # matches=1, fresh (hours_since=5<48): supply_strength=20+30=50;
        # gap = demand(50) - 0.5*50 + 10 (comp<40 bonus, now reachable at comp=0) = 35
        self.assertEqual(rows[0]["gap_score"], 35.0)


if __name__ == "__main__":
    unittest.main()
