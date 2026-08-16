"""Generate a sample daily report from a synthetic candidate set.

No real channels, no live YouTube/vidIQ/Gemini calls: every candidate below
is invented for the fictional "home-fitness gear review" demo vertical (see
config.yaml, competitors.csv, calendar.yaml). It exists so the report
generator (src/report.py, src/taxonomy.py) and the scoring engine
(src/score.py) can be inspected end to end without any credentials.

Run from the repo root:
    python3 -m demo.build_sample_report

Writes reports/<date>_daily.md and appends data/history.csv, exactly as a
real run would (src/report.write_outputs) - the sample committed in this
repo is this script's own output, regenerated whenever the demo dataset
changes.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import common, keyword_demand, report, score  # noqa: E402

DEMO_NOTICE = (
    "> SYNTHETIC DEMO DATA. Every channel, video, and number below is invented\n"
    "> for this portfolio repo's fictional home-fitness-gear-review vertical -\n"
    "> no real channel was scanned and no live API was called to produce it.\n"
    "> Regenerate with `python3 -m demo.build_sample_report`. See demo/README.md.\n\n"
)


def _pub_fields(hours_since: float) -> tuple[str, str]:
    pub_dt = common.now_utc() - timedelta(hours=hours_since)
    return pub_dt.isoformat().replace("+00:00", "Z"), common.to_ist_str(pub_dt)


def _video(channel_id, channel_name, relation, channel_type, subs, lang,
           video_id, title, fmt, hours_since, views, likes, comments) -> dict:
    denom = max(hours_since, 1.0)
    published_at, published_ist = _pub_fields(hours_since)
    return {
        "kind": "video", "format": fmt, "video_id": video_id, "post_url": None,
        "link": common.watch_url(video_id),
        "channel_id": channel_id, "channel_name": channel_name, "relation": relation,
        "channel_type": channel_type, "channel_subs": subs, "lang": lang,
        "title": title, "published_at": published_at, "published_ist": published_ist,
        "hours_since": round(hours_since, 2), "views": views, "likes": likes, "comments": comments,
        "duration_sec": 45 if fmt == "short" else (1800 if fmt == "livestream" else 600),
        "vph": round(views / denom, 2), "like_vph": round(likes / denom, 3),
        "comment_vph": round(comments / denom, 3),
        "eng_rate": round((likes + comments) / views, 5) if views else 0.0,
        "live_status": "concluded" if fmt == "livestream" else "none",
        "thumbnail_url": common.thumb_url(video_id), "thumbnail_read": None,
        "flags": [], "source": "channel",
    }


def _post(channel_id, channel_name, relation, channel_type, subs, lang,
          post_id, title, post_type, poll_options, hours_since, likes) -> dict:
    url = f"https://www.youtube.com/post/{post_id}"
    _, published_ist = _pub_fields(hours_since)
    return {
        "kind": "post", "format": "post", "video_id": None, "post_url": url, "link": url,
        "channel_id": channel_id, "channel_name": channel_name, "relation": relation,
        "channel_type": channel_type, "channel_subs": subs, "lang": lang,
        "title": title, "post_type": post_type, "poll_options": poll_options,
        "published_at": "", "published_ist": published_ist,
        "hours_since": round(hours_since, 1), "views": 0, "likes": likes, "comments": 0,
        "vph": 0.0, "like_vph": 0.0, "comment_vph": 0.0, "eng_rate": 0.0,
        "live_status": "none", "thumbnail_url": None, "thumbnail_read": None,
        "flags": [], "source": "channel",
    }


def build_candidates() -> list[dict]:
    videos = [
        # GearHead Fitness Lab: 3 uploads in-window so the same-run baseline
        # has enough points for a real median - the 3rd is a genuine BREAKOUT.
        _video("UCdemo00000000000000001", "GearHead Fitness Lab", "direct", "channel", 412000, "eng",
               "demoGH01", "The New Budget Kettlebell", "longform", 20, 8000, 600, 90),
        _video("UCdemo00000000000000001", "GearHead Fitness Lab", "direct", "channel", 412000, "eng",
               "demoGH02", "Adjustable Dumbbell Torture Test", "longform", 40, 12000, 700, 80),
        _video("UCdemo00000000000000001", "GearHead Fitness Lab", "direct", "channel", 412000, "eng",
               "demoGH03", "We Did Not Expect This Kettlebell To Win", "short", 5, 45000, 5200, 610),
        # Two more direct competitors piling onto the exact same clickbait
        # "budget kettlebell" hook inside 48h -> 3-channel CONVERGENCE.
        _video("UCdemo00000000000000002", "Iron and Rubber Reviews", "direct", "channel", 367000, "eng",
               "demoIR01", "This Is Your Best Budget Kettlebell", "longform", 30, 6000, 420, 55),
        _video("UCdemo00000000000000003", "The Kettlebell Corner", "direct", "channel", 298000, "eng",
               "demoKC01", "What Is This Budget Kettlebell", "longform", 10, 15000, 1100, 140),
        # Matches the active seasonal calendar phase's boost hooks -> CALENDAR.
        _video("UCdemo00000000000000006", "RepCheck Reviews", "direct", "channel", 198000, "eng",
               "demoRC01", "Back To Gym: Garage Flooring Routine Guide", "longform", 60, 9000, 500, 60),
        _video("UCdemo00000000000000007", "Yoga and Iron", "direct", "channel", 176000, "eng",
               "demoYI01", "5 Yoga Mats That Actually Grip", "short", 8, 22000, 2600, 310),
        _video("UCdemo00000000000000005", "Budget Barbell Co", "direct", "channel", 231000, "eng",
               "demoBB01", "Live Q&A: Home Gym Setup", "livestream", 3, 3000, 210, 95),
        _video("UCdemo00000000000000011", "Sana Lifts", "indirect", "individual", 220000, "eng",
               "demoSL01", "My Home Gym Tour 2026", "longform", 70, 40000, 3200, 250),
        # Own channel, for baseline / coverage-gap comparisons (relation=self
        # is excluded from ranking and convergence, per score.py by design).
        _video("UCdemo00000000000000014", "HomeRack Fitness", "self", "channel", 52000, "mix",
               "demoHR01", "Our Kettlebell Buying Guide", "longform", 15, 1800, 140, 20),
    ]
    posts = [
        _post("UCdemo00000000000000001", "GearHead Fitness Lab", "direct", "channel", 412000, "eng",
              "demopostGH01", "Which kettlebell brand should we test next?", "poll",
              ["CAP Barbell", "Rogue", "Bowflex"], 12, 340),
        _post("UCdemo00000000000000006", "RepCheck Reviews", "direct", "channel", 198000, "eng",
              "demopostRC01", "We hit 200K subscribers today. Thank you!", "text", [], 30, 890),
    ]
    return videos + posts


def main() -> None:
    cfg = common.load_config()
    calendar = common.load_calendar()
    candidates = build_candidates()

    scored, meta = score.score_all(candidates, cfg, calendar)
    demand_section = keyword_demand.build_demand_section(candidates, cfg)

    roster = common.load_competitors()
    n_videos = sum(1 for c in candidates if c.get("kind") == "video")
    n_posts = sum(1 for c in candidates if c.get("kind") == "post")
    n_own = sum(1 for r in roster if r.get("relation") == "self")

    run_info = {
        "date": common.today_ist_date(),
        "yt_units": 0,
        "vidiq_status": "not run (synthetic demo data)",
        "community_status": "not run (synthetic demo data)",
        "thumb_source": "n/a (synthetic demo data)",
        "run_stats": {
            "videos_hydrated": n_videos, "posts_fetched": n_posts, "comments_fetched": 0,
            "channels_scanned": len(roster), "channels_own": n_own,
            "keywords_searched": len(common.load_keywords()), "vidiq_keywords_n": 0,
            "rows_scored": len(scored), "comment_picks": 0,
            "pool_size": len(candidates), "final_picks": cfg["report"]["summary_max_picks"],
            "yt_budget": cfg["quota"]["yt_daily_unit_budget"],
            "ledger_age_days": None,
            "engines": {"clustering": meta.get("cluster_method")},
            "deadline_skipped": [],
        },
    }

    text = report.build_daily_report(scored, meta, cfg, run_info, demand_section)
    text = DEMO_NOTICE + text

    result = report.write_outputs(text, scored, cfg, run_info, kind="daily")
    print(f"Wrote {result['report_path']}")
    print(f"Ledger rows added: {result['history_added']} ({result['ledger_path']})")
    flags_seen = sorted({f for c in scored for f in c.get("flags", [])})
    print(f"Flags exercised in this sample: {', '.join(flags_seen) or '(none)'}")


if __name__ == "__main__":
    main()
