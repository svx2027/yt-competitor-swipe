"""Demand-supply gap signal.

vidIQ keyword research is an MCP tool (session-side), so this module reads its
results from cache/vidiq_keywords.json when the routine session has written
them. Expected shape (list of dicts):
    {"keyword": "...", "volume": 0-100, "competition": 0-100,
     "overall_score": 0-100, "est_monthly_searches": int}

When that cache is absent it degrades to the static keyword universe plus the
"supply strength" computed from the day's own candidate pull, so Section E
always renders something honest.
"""
from __future__ import annotations

import re

from . import common

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Keep domain-specific and year words IN the vocabulary: they define the
# niche, and the overlap threshold below prevents them from over-matching
# on their own.
_STOP = {"the", "a", "an", "to", "for", "of", "in", "on", "and", "or", "how",
         "your", "you", "is", "are", "with"}


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOP and len(t) > 1}


def _required_overlap(kw_tok: set[str]) -> int:
    """Minimum overlapping tokens to count a keyword as matched.

    Scales with the keyword's own length (floor 2 for anything long enough
    to have one) so a single-word keyword - which can contribute at most one
    overlapping token - isn't structurally unmatchable, while a longer
    keyword still needs a real chunk of itself present, not one common word.
    """
    return min(len(kw_tok), max(2, len(kw_tok) // 2))


def load_vidiq_keywords() -> dict:
    raw = common.read_json(common.cache_path("vidiq_keywords.json"), None)
    out = {}
    if not raw:
        return out
    items = raw if isinstance(raw, list) else raw.get("keywords", [])
    for it in items:
        kw = (it.get("keyword") or it.get("term") or "").strip()
        if kw:
            out[kw.lower()] = it
    return out


def _supply_for_keyword(kw: str, candidates: list[dict]) -> dict:
    """How well-served is this query by recent competitor videos?"""
    kw_tok = _tokens(kw)
    if not kw_tok:
        return {"matches": 0, "max_vph": 0.0, "newest_hours": None}
    required = _required_overlap(kw_tok)
    matches, max_vph, newest = 0, 0.0, None
    for c in candidates:
        if c.get("kind") != "video":
            continue
        overlap = kw_tok & _tokens(c.get("title", ""))
        if len(overlap) >= required:
            matches += 1
            max_vph = max(max_vph, c.get("vph", 0.0))
            h = c.get("hours_since")
            if h is not None and (newest is None or h < newest):
                newest = h
    return {"matches": matches, "max_vph": round(max_vph, 1), "newest_hours": newest}


def best_keyword_match(title: str, kw_metrics: dict, universe: list[str]) -> tuple[str, float]:
    """Return (keyword, demand_alignment 0-100) for a candidate title.

    Alignment = the matched keyword's vidIQ overall score (how valuable the query
    is), or a modest computed value when vidIQ data is absent. This is a ranking
    input; the DEMAND_GAP *flag* (genuine under-served query) is decided in
    annotate_candidates using competition + overall together.
    """
    title_tok = _tokens(title)
    if not title_tok:
        return "", 0.0
    best_kw, best_overlap = "", 0
    pool = list(kw_metrics.keys()) + [k.lower() for k in universe]
    for kw in pool:
        kw_tok = _tokens(kw)
        if not kw_tok:
            continue
        ov = len(title_tok & kw_tok)
        # each candidate needs its OWN required overlap (scales with its
        # length), not a flat 2 - otherwise a single-word keyword can never
        # register, since it can contribute at most one overlapping token
        if ov >= _required_overlap(kw_tok) and ov > best_overlap:
            best_overlap, best_kw = ov, kw
    if not best_kw:
        return "", 0.0
    m = kw_metrics.get(best_kw)
    if m:
        return best_kw, round(float(m.get("overall_score", 0) or 0), 1)
    return best_kw, round(common.clamp(30 + 8 * best_overlap, 0, 60), 1)


def build_demand_section(candidates: list[dict], cfg: dict) -> list[dict]:
    """Section E: rising queries with thin or stale supply."""
    kw_metrics = load_vidiq_keywords()
    universe = common.load_keywords()
    keys = list(kw_metrics.keys()) if kw_metrics else [k.lower() for k in universe]
    rows = []
    for kw in keys:
        m = kw_metrics.get(kw, {})
        supply = _supply_for_keyword(kw, candidates)
        vol = float(m.get("volume", 0) or 0)
        raw_comp = m.get("competition")
        comp = float(raw_comp) if raw_comp is not None else 0.0
        score = float(m.get("overall_score", 0) or 0)
        # demand: vidIQ score/volume if present, else neutral baseline
        demand = score if kw_metrics else 50.0
        # supply penalty: more fresh/strong matches => smaller gap
        newest = supply["newest_hours"]
        fresh = supply["matches"] > 0 and newest is not None and newest < 48
        supply_strength = min(supply["matches"] * 20 + (30 if fresh else 0), 100)
        gap = common.clamp(demand - 0.5 * supply_strength + (10 if comp < 40 else 0), 0, 100)
        stale = supply["matches"] == 0 or newest is None or newest > 168
        rows.append({
            "keyword": kw,
            "volume": vol, "competition": comp, "overall_score": score,
            "est_monthly_searches": m.get("est_monthly_searches"),
            "supply_matches": supply["matches"],
            "supply_newest_hours": supply["newest_hours"],
            "supply_max_vph": supply["max_vph"],
            "stale_or_thin": stale,
            "gap_score": round(gap, 1),
            "has_vidiq": bool(m),
        })
    rows.sort(key=lambda r: (r["gap_score"], r["overall_score"]), reverse=True)
    return rows


def annotate_candidates(candidates: list[dict], cfg: dict) -> None:
    """Attach demand alignment + matched keyword, and flag DEMAND_GAP only for
    genuine under-served queries (high overall score AND low competition)."""
    kw_metrics = load_vidiq_keywords()
    universe = common.load_keywords()
    threshold = cfg["flags"]["demand_gap_min_score"]
    max_competition = cfg["flags"].get("demand_gap_max_competition", 32)
    for c in candidates:
        if c.get("kind") != "video":
            c["demand_gap_score"] = 0.0
            continue
        kw, align = best_keyword_match(c.get("title", ""), kw_metrics, universe)
        c["demand_keyword"] = kw
        c["demand_gap_score"] = align
        m = kw_metrics.get(kw, {})
        raw_comp = m.get("competition")
        comp = float(raw_comp) if raw_comp is not None else 100.0
        # genuine gap = strong query (overall >= threshold) that is under-served
        # (low competition). Plain alignment alone does NOT flag.
        if m and align >= threshold and comp < max_competition and "DEMAND_GAP" not in c["flags"]:
            c["flags"].append("DEMAND_GAP")
