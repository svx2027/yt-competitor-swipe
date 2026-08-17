"""Opportunity scoring: outlier multiplier, engagement-velocity z-scores,
demand gap, cross-competitor convergence, calendar tailwind, sleeper
re-acceleration, packaging flags, and the blended 0-100 Opportunity Score.

Clustering uses the Gemini fast model when available, with a deterministic
local fallback (token-overlap connected components) so the signal never
depends on an external API being up.
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict

from . import common, keyword_demand

_TOKEN_RE = re.compile(r"[a-z0-9']+")
# Cross-niche English filler words - a fixed default tuned for this repo's
# English-language demo corpus. A deployment on a different-language corpus
# would extend or replace this set via config.yaml, the same way
# niche.cluster_anchor_tokens already is.
_GENERIC = {
    "the", "a", "an", "to", "for", "of", "in", "on", "and", "or", "how", "your",
    "you", "is", "are", "with", "this", "that", "best", "new", "full", "video",
    "live", "session", "class", "ep", "part", "free", "by", "from", "what",
    "official", "time", "vs", "top", "review",
}
# Domain tokens explicitly KEPT as cluster anchors even when corpus-ubiquitous
# (e.g. a subject-code abbreviation can be common across this niche's titles
# but still be a meaningful subtopic anchor). Vertical-specific:
# config.yaml niche.cluster_anchor_tokens, loaded by the caller and passed in.


def _sig_tokens(title: str, keep: set[str]) -> set[str]:
    toks = set()
    for t in _TOKEN_RE.findall((title or "").lower()):
        if t in keep:
            toks.add(t)
        elif t not in _GENERIC and len(t) > 2 and not t.isdigit():
            toks.add(t)
    return toks


# --------------------------------------------------------------------------- #
# Clustering
# --------------------------------------------------------------------------- #
def _filtered_token_sets(videos: list[dict], keep: set[str], max_df: float = 0.4) -> list[set]:
    """Significant tokens per title, with corpus-ubiquitous tokens removed.

    A token appearing in more than `max_df` of titles (e.g. a channel's own
    brand name, or a recurring filler word) carries no subtopic signal and
    would connect everything, so we drop it unless it is an explicit domain
    anchor in `keep`.
    """
    raw = [_sig_tokens(v.get("title", ""), keep) for v in videos]
    n = len(raw)
    if n == 0:
        return raw
    df = Counter()
    for s in raw:
        df.update(s)
    drop = {t for t, c in df.items() if t not in keep and c > max_df * n}
    return [s - drop for s in raw]


def _local_clusters(token_sets: list[set]) -> list[list[int]]:
    """Group titles by their single most-distinctive (rarest) token.

    Anchor grouping instead of single-link union-find: union-find chains titles
    transitively through common bridge tokens and collapses a large corpus into
    one mega-cluster. Grouping each title under its rarest significant token
    yields tight, specific subtopics instead and cannot form a mega-cluster.
    """
    df = Counter()
    for s in token_sets:
        df.update(s)
    groups = defaultdict(list)
    for i, s in enumerate(token_sets):
        if not s:
            groups[("__singleton__", i)].append(i)  # ungroupable title
        else:
            anchor = min(s, key=lambda t: (df[t], t))  # rarest token, ties alphabetical
            groups[anchor].append(i)
    return list(groups.values())


def _gemini_clusters(videos: list[dict], model: str, example_subtopics: list[str]) -> list[list[int]] | None:
    """Ask Gemini fast to cluster titles into subtopics. Returns index groups or None."""
    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        titles = [f"{i}: {v.get('title','')}" for i, v in enumerate(videos)]
        examples = ", ".join(f"'{s}'" for s in example_subtopics)
        prompt = (
            f"Cluster these YouTube video titles by SUBTOPIC (e.g. {examples}). "
            "Return ONLY JSON: a list of "
            "clusters, each a list of the integer ids that belong together. Every id "
            "appears exactly once.\n\n" + "\n".join(titles)
        )
        resp = client.models.generate_content(model=model, contents=prompt)
        import json
        text = (resp.text or "").strip()
        text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
        groups = json.loads(text)
        flat = sorted(i for g in groups for i in g)
        if flat == list(range(len(videos))):
            return groups
    except BaseException:  # noqa: BLE001, pyo3 PanicException inherits BaseException; fall back to local
        return None
    return None


def cluster_videos(videos: list[dict], token_sets: list[set], cfg: dict) -> tuple[str, list[list[int]]]:
    gem = cfg.get("gemini", {})
    if gem.get("enabled") and len(videos) <= gem.get("cluster_batch", 60):
        model = os.environ.get(gem.get("fast_env", "GEMINI_MODEL_FAST")) or gem.get("fast_default")
        if model:
            examples = cfg["niche"]["cluster_example_subtopics"]
            groups = _gemini_clusters(videos, model, examples)
            if groups is not None:
                return "gemini", groups
    return "local", _local_clusters(token_sets)


def _cluster_label(token_sets: list[set], idxs: list[int]) -> str:
    """Top-3 most frequent tokens across the cluster's titles.

    Sets iterate in an order tied to Python's per-process string-hash seed,
    so updating the counter straight from each set makes count-ties between
    tokens (and therefore which 3 make the label) resolve differently run to
    run on identical input. Sorting each set before counting fixes the
    insertion order the tie-break depends on.
    """
    counter = Counter()
    for i in idxs:
        counter.update(sorted(token_sets[i]))
    common_toks = [t for t, _ in counter.most_common(3)]
    return " / ".join(common_toks) if common_toks else "misc"


# --------------------------------------------------------------------------- #
# Outlier
# --------------------------------------------------------------------------- #
def compute_outliers(videos: list[dict], cfg: dict) -> None:
    """Outlier multiplier = views vs the channel's own expected pace at this age.

    Priority: vidIQ outlier/breakout score (preferred) -> computed vs the
    channel's recent-uploads baseline (cache/baselines.json) -> computed vs the
    channel's same-run median (weakest, only if no baseline exists).
    """
    vidiq = common.read_json(common.cache_path("vidiq_outliers.json"), {}) or {}
    baselines = common.read_json(common.cache_path("baselines.json"), {}) or {}
    by_channel = defaultdict(list)
    for v in videos:
        by_channel[v["channel_id"]].append(v)
    chan_med_vph = {}
    for cid, vs in by_channel.items():
        vphs = sorted(x["vph"] for x in vs if x["vph"] > 0)
        if vphs:
            chan_med_vph[cid] = vphs[len(vphs) // 2]
    for v in videos:
        vq = vidiq.get(v["video_id"]) if v.get("video_id") else None
        if vq:
            score = vq.get("outlier_score", vq.get("breakoutScore", vq.get("score")))
            if score is not None:
                v["outlier"] = round(float(score), 2)
                v["outlier_source"] = "vidiq"
                continue
        # computed proxies: lifetime-VPH baselines understate "expected fresh
        # VPH", so the raw ratio can balloon. Sanity-cap the DISPLAYED value at
        # 20x (the score component already clamps at 5x); vidIQ is preferred.
        base = (baselines.get(v["channel_id"]) or {}).get("median_vph")
        if base and base > 0:
            v["outlier"] = round(min(v["vph"] / base, 20.0), 2)
            v["outlier_source"] = "baseline"
            continue
        med = chan_med_vph.get(v["channel_id"], 0)
        v["outlier"] = round(min(v["vph"] / med, 20.0), 2) if med > 0 else 1.0
        v["outlier_source"] = "same-run"


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #
def active_phase(calendar: dict) -> dict | None:
    today = common.today_ist_date()
    for ph in calendar.get("phases", []):
        if ph["start"] <= today <= ph["end"]:
            return ph
    return None


def apply_calendar(videos: list[dict], calendar: dict) -> dict | None:
    phase = active_phase(calendar)
    if not phase:
        for v in videos:
            v["calendar_phase"], v["calendar_boost"] = None, 0.0
        return None
    hook_tokens = [set(_TOKEN_RE.findall(h.lower())) for h in phase.get("boost_hooks", [])]
    for v in videos:
        ttok = set(_TOKEN_RE.findall((v.get("title", "")).lower()))
        best = 0.0
        for hk in hook_tokens:
            if not hk:
                continue
            ov = len(ttok & hk) / len(hk)
            best = max(best, ov)
        v["calendar_phase"] = phase["key"]
        v["calendar_boost"] = round(common.clamp(best, 0, 1), 2)
        if best >= 0.5 and "CALENDAR" not in v["flags"]:
            v["flags"].append("CALENDAR")
    return phase


# --------------------------------------------------------------------------- #
# Sleeper + new format (history-dependent, best-effort)
# --------------------------------------------------------------------------- #
def apply_history_signals(videos: list[dict], cfg: dict) -> None:
    hist = common.read_history(cfg["output"]["history_csv"])
    if not hist:
        return
    last_vph, seen_formats, chan_rows = {}, defaultdict(set), Counter()
    for row in hist:
        vid = row.get("video_or_post_id", "")
        try:
            last_vph[vid] = float(row.get("vph") or 0)
        except ValueError:
            pass
        ch = row.get("channel", "")
        seen_formats[ch].add(row.get("format", ""))
        chan_rows[ch] += 1
    min_age = cfg["sleeper"]["min_age_hours"]
    growth = cfg["sleeper"]["min_vph_growth_pct"] / 100.0
    new_fmt_min_rows = cfg["flags"].get("new_format_min_history_rows", 8)
    for v in videos:
        prev = last_vph.get(v.get("video_id"))
        if prev and v["hours_since"] >= min_age and prev > 0:
            if v["vph"] >= prev * (1 + growth):
                if "SLEEPER" not in v["flags"]:
                    v["flags"].append("SLEEPER")
                v["sleeper_prev_vph"] = round(prev, 2)
        # Only call a format "new" once we have enough history for that channel to
        # judge - otherwise thin history makes every format look new.
        ch = v.get("channel_name")
        fmts = seen_formats.get(ch)
        if (fmts and chan_rows[ch] >= new_fmt_min_rows and v["format"] not in fmts
                and "NEW_FORMAT" not in v["flags"]):
            v["flags"].append("NEW_FORMAT")


# --------------------------------------------------------------------------- #
# Main scoring
# --------------------------------------------------------------------------- #
def _pct_rank(value: float, sorted_vals: list[float]) -> float:
    if not sorted_vals:
        return 0.0
    below = sum(1 for x in sorted_vals if x < value)
    return 100.0 * below / len(sorted_vals)


def score_all(candidates: list[dict], cfg: dict, calendar: dict) -> tuple[list[dict], dict]:
    videos = [c for c in candidates if c.get("kind") == "video"]
    posts = [c for c in candidates if c.get("kind") == "post"]

    # z-scores across the day's video distribution
    if videos:
        vph_z = common.zscores([v["vph"] for v in videos])
        cvph_z = common.zscores([v["comment_vph"] for v in videos])
        lvph_z = common.zscores([v["like_vph"] for v in videos])
        er_z = common.zscores([v["eng_rate"] for v in videos])
        ew = cfg["engagement_subweights"]
        for i, v in enumerate(videos):
            v["vph_z"] = round(vph_z[i], 2)
            v["comment_vph_z"] = round(cvph_z[i], 2)
            v["like_vph_z"] = round(lvph_z[i], 2)
            v["eng_rate_z"] = round(er_z[i], 2)
            v["engagement_velocity"] = round(
                ew["comment_vph_z"] * cvph_z[i] + ew["like_vph_z"] * lvph_z[i]
                + ew["eng_rate_z"] * er_z[i], 3)

    compute_outliers(videos, cfg)
    keyword_demand.annotate_candidates(videos, cfg)
    phase = apply_calendar(videos, calendar)

    # convergence via clustering, scoped to COMPETITOR videos (self excluded:
    # convergence is about competitors piling onto a hook, not our own uploads)
    cluster_method = "none"
    for v in videos:
        v.setdefault("cluster_id", None)
        v.setdefault("cluster_label", None)
        v.setdefault("convergence_size", 0)
    comp_videos = [v for v in videos if v.get("relation") != "self"]
    if comp_videos:
        keep_tokens = set(cfg["niche"]["cluster_anchor_tokens"])
        token_sets = _filtered_token_sets(comp_videos, keep_tokens, cfg["convergence"].get("cluster_max_df", 0.4))
        cluster_method, groups = cluster_videos(comp_videos, token_sets, cfg)
        win = cfg["convergence"]["window_hours"]
        min_sz = cfg["convergence"]["min_cluster_size"]
        for gi, idxs in enumerate(groups):
            label = _cluster_label(token_sets, idxs)
            recent = [i for i in idxs
                      if comp_videos[i]["hours_since"] is not None and comp_videos[i]["hours_since"] <= win]
            channels = {comp_videos[i]["channel_id"] for i in recent}
            conv = len(channels)
            for i in idxs:
                comp_videos[i]["cluster_id"] = gi
                comp_videos[i]["cluster_label"] = label
                comp_videos[i]["convergence_size"] = conv
                if conv >= min_sz and "CONVERGENCE" not in comp_videos[i]["flags"]:
                    comp_videos[i]["flags"].append("CONVERGENCE")

    apply_history_signals(videos, cfg)

    # flags: breakout, hot engagement
    fl = cfg["flags"]
    for v in videos:
        if (v.get("outlier") or 0) >= fl["breakout_outlier_min"] and "BREAKOUT" not in v["flags"]:
            v["flags"].append("BREAKOUT")
        if (v.get("comment_vph_z") or 0) >= fl["hot_engagement_z_min"] and "HOT_ENGAGEMENT" not in v["flags"]:
            v["flags"].append("HOT_ENGAGEMENT")

    # Opportunity Score components (each 0-100)
    w = cfg["weights"]
    rel_w = cfg["relation_weights"]
    sorted_vph = sorted(v["vph"] for v in videos)
    outlier_cap = 5.0
    conv_cap = cfg["convergence"]["min_cluster_size"] + 2
    for v in videos:
        c_vph = _pct_rank(v["vph"], sorted_vph)
        c_out = common.clamp((v.get("outlier") or 0) / outlier_cap * 100, 0, 100)
        c_eng = common.clamp(50 + 20 * (v.get("engagement_velocity") or 0), 0, 100)
        c_dem = v.get("demand_gap_score") or 0
        c_conv = common.clamp((v.get("convergence_size") or 0) / conv_cap * 100, 0, 100)
        c_cal = (v.get("calendar_boost") or 0) * 100
        raw = (w["vph"] * c_vph + w["outlier"] * c_out + w["engagement"] * c_eng
               + w["demand_gap"] * c_dem + w["convergence"] * c_conv
               + w["calendar"] * c_cal) / 100.0
        v["opportunity_raw"] = round(raw, 1)
        v["opportunity_score"] = round(raw * rel_w.get(v["relation"], 1.0), 1)
        v["_components"] = {"vph": round(c_vph, 1), "outlier": round(c_out, 1),
                            "engagement": round(c_eng, 1), "demand_gap": round(c_dem, 1),
                            "convergence": round(c_conv, 1), "calendar": round(c_cal, 1)}

    # posts: lighter score from engagement + poll + calendar + demand keyword
    _score_posts(posts, cfg, calendar)

    videos.sort(key=lambda v: v["opportunity_score"], reverse=True)
    posts.sort(key=lambda p: p["opportunity_score"], reverse=True)

    meta = {
        "cluster_method": cluster_method,
        "active_phase": phase["key"] if phase else None,
        "active_phase_label": phase["label"] if phase else None,
        "n_videos": len(videos), "n_posts": len(posts),
    }
    return videos + posts, meta


def _score_posts(posts: list[dict], cfg: dict, calendar: dict) -> None:
    if not posts:
        return
    phase = active_phase(calendar)
    hook_tokens = [set(_TOKEN_RE.findall(h.lower())) for h in (phase.get("boost_hooks", []) if phase else [])]
    likes_sorted = sorted(p.get("likes", 0) for p in posts)
    rel_w = cfg["relation_weights"]
    for p in posts:
        c_like = _pct_rank(p.get("likes", 0), likes_sorted)
        poll_bonus = 100 if p.get("post_type") == "poll" else 0
        ttok = set(_TOKEN_RE.findall((p.get("title", "")).lower()))
        cal = 0.0
        for hk in hook_tokens:
            if hk:
                cal = max(cal, len(ttok & hk) / len(hk))
        p["calendar_phase"] = phase["key"] if phase else None
        p["calendar_boost"] = round(cal, 2)
        p["outlier"] = None
        p["vph"] = 0.0
        raw = 0.45 * c_like + 0.35 * poll_bonus + 0.20 * cal * 100
        p["opportunity_raw"] = round(raw, 1)
        p["opportunity_score"] = round(raw * rel_w.get(p["relation"], 1.0), 1)
        if cal >= 0.5 and "CALENDAR" not in p["flags"]:
            p["flags"].append("CALENDAR")
        if p.get("post_type") == "poll" and "HOT_ENGAGEMENT" not in p["flags"]:
            p["flags"].append("HOT_ENGAGEMENT")
