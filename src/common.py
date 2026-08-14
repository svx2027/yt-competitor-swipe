"""Shared helpers, config loading, time/maths utilities and the candidate schema.

Every candidate (video or community post) is a plain dict with the keys
documented in CANDIDATE_FIELDS. Modules enrich the dict in place:
  youtube_pull / community_pull -> raw signal fields
  score                         -> outlier, z-scores, flags, opportunity_score
  vision                        -> thumbnail_read
  report (session)              -> why, strategist_take
"""
from __future__ import annotations

import csv
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Fixed UTC+5:30 (no DST, so a static offset is correct here). A deployment
# spanning other timezones would make this per-vertical config, the same way
# config_path()/calendar_path() already are.
IST = timezone(timedelta(hours=5, minutes=30))

# Load secrets from the project .env explicitly (avoids dotenv's stack-walk bug).
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def vertical() -> str:
    """VERTICAL env var, defaulting to 'main'. Selects which niche's
    config/calendar/keywords/competitors/taxonomy files this process reads.

    Unset or 'main' (case-insensitive) is the default vertical: every path
    resolver below returns the repo-root filenames, so a single-niche setup
    is byte-for-byte unchanged. Any other value resolves to that vertical's
    files under verticals/<name>/, so the same engine can track more than one
    niche side by side (e.g. two different channels or subject areas) without
    their configs colliding."""
    return (os.environ.get("VERTICAL") or "main").strip().lower() or "main"


def _vertical_path(root_relpath: str, vertical_relpath: str) -> Path:
    """main (default/unset) -> PROJECT_ROOT/root_relpath. Any other VERTICAL
    -> PROJECT_ROOT/verticals/<vertical>/vertical_relpath."""
    v = vertical()
    if v == "main":
        return PROJECT_ROOT / root_relpath
    return PROJECT_ROOT / "verticals" / v / vertical_relpath


def config_path() -> Path:
    return _vertical_path("config.yaml", "config.yaml")


def calendar_path() -> Path:
    return _vertical_path("calendar.yaml", "calendar.yaml")


def keywords_path() -> Path:
    return _vertical_path("keywords.txt", "keywords.txt")


def competitors_path() -> Path:
    return _vertical_path("competitors.csv", "competitors.csv")


def taxonomy_path() -> Path:
    return _vertical_path("config/taxonomy.yml", "taxonomy.yml")


def confirmations_path() -> Path:
    """Weekly outcome-confirmation fallback file. Per vertical: two verticals
    running in the same ISO week must never read or overwrite each other's
    pending confirmations."""
    return _vertical_path("data/confirmations.yml", "data/confirmations.yml")


def load_config() -> dict:
    with open(config_path(), "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_calendar() -> dict:
    with open(calendar_path(), "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_keywords() -> list[str]:
    with open(keywords_path(), "r", encoding="utf-8") as fh:
        return [ln.strip() for ln in fh if ln.strip()]


def load_competitors() -> list[dict]:
    with open(competitors_path(), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"Missing required env var {name} (set it in .env)")
    return val


# --------------------------------------------------------------------------- #
# Time
# --------------------------------------------------------------------------- #
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 string (handles trailing Z) into an aware UTC dt."""
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hours_since(dt: datetime, ref: datetime | None = None) -> float:
    ref = ref or now_utc()
    return max((ref - dt).total_seconds() / 3600.0, 0.0)


def to_ist_str(dt: datetime) -> str:
    if dt is None:
        return ""
    return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def today_ist_date() -> str:
    return now_utc().astimezone(IST).strftime("%Y-%m-%d")


def past_deadline(deadline_hhmm: str | None, now: datetime | None = None) -> bool:
    """Deadline watchdog: True once IST wall-clock reaches HH:MM today.

    `deadline_hhmm` like "09:00" (IST). None disables the watchdog (local runs).
    `now` is injectable for tests. Same-day semantics only: routines fire less
    than an hour before their deadline, so no midnight-crossing logic.
    """
    if not deadline_hhmm:
        return False
    now_ist = (now or now_utc()).astimezone(IST)
    try:
        h, m = (int(x) for x in deadline_hhmm.strip().split(":"))
    except ValueError:
        return False
    return (now_ist.hour, now_ist.minute) >= (h, m)


# --------------------------------------------------------------------------- #
# Maths
# --------------------------------------------------------------------------- #
def zscores(values: list[float]) -> list[float]:
    """Population z-scores. Returns 0.0 for every element if std == 0."""
    n = len(values)
    if n == 0:
        return []
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(var)
    if std == 0:
        return [0.0] * n
    return [(v - mean) / std for v in values]


def safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------- #
# Links
# --------------------------------------------------------------------------- #
def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def thumb_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


# --------------------------------------------------------------------------- #
# Cache / IO
# --------------------------------------------------------------------------- #
def cache_path(name: str) -> Path:
    return PROJECT_ROOT / "cache" / name


def read_json(path: Path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, default=str)


# --------------------------------------------------------------------------- #
# Master ledger (data/history.csv, tracked in git). Header-driven everywhere:
# rows are dicts keyed by column name, never positional. The outcome-loop
# columns: topic (taxonomy label, immutable once non-empty), executed
# (yes/no/auto/pending/""), executed_video_id, outcome_vph_ratio.
# --------------------------------------------------------------------------- #
HISTORY_FIELDS = [
    "date", "format", "channel", "relation", "title", "video_or_post_id",
    "published_at", "views", "vph", "outlier", "comments", "comment_vph",
    "eng_rate", "flags", "opportunity_score",
    "topic", "executed", "executed_video_id", "outcome_vph_ratio",
]


def candidate_to_history_row(c: dict, date: str, topic: str = "",
                             executed: str = "") -> dict:
    return {
        "date": date,
        "format": c.get("format", ""),
        "channel": c.get("channel_name", ""),
        "relation": c.get("relation", ""),
        "title": (c.get("title", "") or "").replace("\n", " ").strip(),
        "video_or_post_id": c.get("video_id") or c.get("post_url") or "",
        "published_at": c.get("published_at", ""),
        "views": c.get("views", 0),
        "vph": round(c.get("vph", 0) or 0, 2),
        "outlier": round(c.get("outlier") or 0, 2),
        "comments": c.get("comments", 0),
        "comment_vph": round(c.get("comment_vph", 0) or 0, 3),
        "eng_rate": round(c.get("eng_rate", 0) or 0, 4),
        "flags": "|".join(c.get("flags", [])),
        "opportunity_score": round(c.get("opportunity_score", 0) or 0, 1),
        "topic": topic,
        "executed": executed,
        "executed_video_id": "",
        "outcome_vph_ratio": "",
    }


def _read_ledger_raw(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def _write_ledger(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HISTORY_FIELDS})


def append_history(rows: list[dict], path: str,
                   dedupe_keys=("date", "video_or_post_id")) -> int:
    """Append rows to the ledger, idempotent on (date, id). Header-driven:
    an older on-disk schema is migrated in place (new columns filled empty).
    For existing rows, an empty `topic` may be filled by an incoming non-empty
    one (a tag, once written, is never changed)."""
    p = PROJECT_ROOT / path
    existing = _read_ledger_raw(p)
    by_key = {tuple(str(r.get(k, "")) for k in dedupe_keys): r for r in existing}
    added = 0
    for r in rows:
        key = tuple(str(r.get(k, "")) for k in dedupe_keys)
        if key in by_key:
            cur = by_key[key]
            if not (cur.get("topic") or "").strip() and (r.get("topic") or "").strip():
                cur["topic"] = r["topic"]
            continue
        by_key[key] = {k: r.get(k, "") for k in HISTORY_FIELDS}
        added += 1
    _write_ledger(p, list(by_key.values()))
    return added


def update_history_rows(path: str, updates: dict,
                        executed_only_if: tuple = ("", "pending")) -> int:
    """Targeted column updates keyed by video_or_post_id (header-driven).
    Guards: `topic` only fills when currently empty; `executed` only changes
    when the current value is in `executed_only_if` (outcome sync passes
    ("pending",) so non-pick snapshot rows are untouched); ratio +
    executed_video_id may be (re)set."""
    p = PROJECT_ROOT / path
    rows = _read_ledger_raw(p)
    changed = 0
    for r in rows:
        upd = updates.get(r.get("video_or_post_id", ""))
        if not upd:
            continue
        touched = False
        eligible_exec = (r.get("executed") or "") in executed_only_if
        for col, val in upd.items():
            if col == "topic":
                if (r.get("topic") or "").strip():
                    continue
            elif col in ("executed", "executed_video_id"):
                # both move only together with an allowed executed transition;
                # once confirmed, neither can be rewritten
                if not eligible_exec:
                    continue
            elif col == "outcome_vph_ratio":
                if (r.get("executed") or "") not in ("yes", "auto"):
                    continue
            else:
                continue  # other columns are immutable through this path
            if r.get(col, "") != str(val):
                r[col] = val
                touched = True
        changed += 1 if touched else 0
    if changed:
        _write_ledger(p, rows)
    return changed


def read_history(path: str) -> list[dict]:
    p = PROJECT_ROOT / path
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def ledger_age_days(path: str) -> int | None:
    """Days between today (IST) and the newest `date` in the ledger; None if
    the ledger is missing or empty (callers must handle both gracefully)."""
    rows = read_history(path)
    dates = sorted(r.get("date", "") for r in rows if r.get("date"))
    if not dates:
        return None
    try:
        newest = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (now_utc().astimezone(IST).date() - newest).days


# --------------------------------------------------------------------------- #
# Candidate schema (documentation only)
# --------------------------------------------------------------------------- #
CANDIDATE_FIELDS = """
kind: 'video' | 'post'
format: 'longform' | 'short' | 'livestream' | 'post'
video_id, post_url, link
channel_id, channel_name, relation, channel_type, channel_subs, lang
title, published_at (ISO UTC), published_ist, hours_since
views, likes, comments, duration_sec
vph, like_vph, comment_vph, eng_rate
live_status: 'none'|'live'|'upcoming'|'concluded'
thumbnail_url, thumbnail_read
outlier, outlier_source, vph_z, comment_vph_z, like_vph_z, eng_rate_z
engagement_velocity, demand_gap_score, convergence_size, cluster_id, cluster_label
calendar_phase, calendar_boost, flags[]
opportunity_raw, opportunity_score
why, strategist_take
"""
