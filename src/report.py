"""Assemble the plain-text report (Google Docs / WhatsApp portable: no markdown
tables, no em dashes), write the local history CSV + outbox payloads (email,
sheet rows) for the routine session to deliver via Gmail/Drive connectors.

"Why it's working" and the strategist's take are session-authored per the
brief (the take's on-page label comes from cfg["report"]["take_label"]). This
module fills deterministic, data-derived fallbacks so the file is always
complete, and merges richer narratives when the session supplies them via
cache/narratives.json keyed by video_id / post_url.
"""
from __future__ import annotations

from . import common

SEP = "=" * 58
SUB = "-" * 58


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def fmt_subs(n) -> str:
    n = common.safe_int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n) if n else "n/a"


def fmt_hours(h) -> str:
    if h is None:
        return "?"
    if h < 1:
        return f"{int(h*60)}m ago"
    if h < 48:
        return f"{h:.1f}h ago"
    return f"{h/24:.1f}d ago"


def channel_line(c: dict) -> str:
    return f"{c.get('channel_name','?')} ({c.get('relation','?')}, {c.get('channel_type','?')}, {fmt_subs(c.get('channel_subs'))} subs)"


# --------------------------------------------------------------------------- #
# Preface (auto-generated from run_stats collected during the run)
# --------------------------------------------------------------------------- #
def estimate_manual_hours(rs: dict) -> float:
    """Rough manual-equivalent: what the same sweep would cost a human.
    Model: 3 min/video judged, 1.5 min/post, 8 s/comment read, 1 min/channel
    swept, +30 min keyword research when vidIQ data was used."""
    minutes = (
        rs.get("videos_hydrated", 0) * 3
        + rs.get("posts_fetched", 0) * 1.5
        + rs.get("comments_fetched", 0) * 8 / 60
        + rs.get("channels_scanned", 0) * 1
        + (30 if rs.get("vidiq_keywords_n", 0) else 0)
    )
    return round(minutes / 60 * 2) / 2  # nearest half hour


def build_preface(rs: dict, kind: str, cfg: dict) -> str:
    """One-minute, pitch-tone preface. Every number comes from run_stats."""
    L = []
    L.append(SUB)
    L.append("PREFACE: WHAT THIS RUN DID")
    L.append(SUB)
    fmts = rs.get("formats_covered") or []
    own = rs.get("channels_own", 0)
    comp = max(rs.get("channels_scanned", 0) - own, 0)
    L.append(
        f"Scanned {comp} competitor channels plus {own} own channel(s) across "
        f"{', '.join(fmts) if fmts else 'video'} - every upload in the window, "
        f"not a sample."
    )
    kw_line = f"Searched {rs.get('keywords_searched', 0)} seed keywords"
    if rs.get("vidiq_keywords_n"):
        kw_line += f" and matched against {rs['vidiq_keywords_n']} vidIQ-expanded demand queries"
    L.append(kw_line + ".")
    L.append(
        f"Fetched {rs.get('videos_hydrated', 0)} videos and {rs.get('posts_fetched', 0)} "
        f"community posts; scored {rs.get('rows_scored', 0)} rows on VPH, outlier, "
        f"engagement velocity, demand gap, convergence and calendar fit."
    )
    L.append(
        "Outlier logic: vidIQ breakout score where available, else each video's "
        "VPH vs its own channel's recent-uploads baseline - so a small channel's "
        "hit ranks on merit, not size."
    )
    L.append(cfg["report"]["niche_filter_note"])
    if rs.get("comments_fetched"):
        L.append(
            f"Mined {rs['comments_fetched']} viewer comments across the top "
            f"{rs.get('comment_picks', 0)} picks for the Audience read sections."
        )
    L.append(
        f"Funnel: {rs.get('pool_size', 0)} candidates -> {rs.get('final_picks', 0)} "
        f"ranked picks on Page 1. YouTube quota used: {rs.get('yt_units', 0)} of "
        f"{rs.get('yt_budget', 9000)} units."
    )
    age = rs.get("ledger_age_days")
    if age is None:
        L.append("Ledger: starting fresh - data/history.csv was empty or absent; "
                 "durable signals (sleepers, outcomes) build from today.")
    else:
        L.append(f"Ledger: {rs.get('ledger_rows', 0)} rows, newest snapshot "
                 f"{age} day(s) old; sleeper and outcome signals are live.")
    engines = rs.get("engines") or {}
    eng_bits = []
    if engines.get("clustering"):
        eng_bits.append(f"clustering: {engines['clustering']}")
    if engines.get("thumbnails"):
        eng_bits.append(f"thumbnails: {engines['thumbnails']}")
    if engines.get("community"):
        eng_bits.append(f"community: {engines['community']}")
    if engines.get("vidiq"):
        eng_bits.append(f"vidIQ: {engines['vidiq']}")
    if eng_bits:
        L.append("Engines: " + "; ".join(eng_bits) + ".")
    skipped = rs.get("deadline_skipped") or []
    if skipped:
        L.append(
            "DEADLINE NOTE: the delivery watchdog fired; skipped this run: "
            + ", ".join(skipped) + ". Core scan and scoring were NOT affected."
        )
    hours = estimate_manual_hours(rs)
    L.append(
        f"Doing this sweep by hand - opening every channel, judging every upload, "
        f"reading the comments - is roughly {hours:g} hours of work. It was on "
        f"your desk before the deadline."
    )
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Deterministic fallback narratives (session can override)
# --------------------------------------------------------------------------- #
def make_this_call(c: dict, cfg: dict) -> str:
    fmt = c.get("format")
    flags = c.get("flags", [])
    verb = {"short": "Remix as a Short", "longform": "Remix as a longform",
            "livestream": "Counter-program live", "post": "Echo as a community post"}.get(fmt, "Remix")
    if "BREAKOUT" in flags:
        return f"{verb}: packaging is over-indexing for the channel"
    if "CONVERGENCE" in flags:
        return f"{verb}: multiple competitors are piling onto this hook now"
    if "DEMAND_GAP" in flags:
        return f"{verb}: rising query with thin or stale supply"
    if "HOT_ENGAGEMENT" in flags:
        return f"{verb}: fast comments signal high idea-value"
    if "CALENDAR" in flags:
        return f"{verb}: rides the live {cfg['report']['calendar_cycle_label']} phase"
    return f"{verb}: strong views-per-hour vs the field"


def fallback_why(c: dict) -> str:
    bits = []
    comp = c.get("_components", {})
    if c.get("vph"):
        bits.append(f"VPH {fmt_int(round(c['vph']))} (top {max(0, 100 - comp.get('vph', 0)):.0f}% of the field).")
    if (c.get("outlier") or 0) >= 1.5:
        bits.append(f"Doing {c['outlier']}x the channel's own expected pace ({c.get('outlier_source')}).")
    if (c.get("comment_vph_z") or 0) >= 1:
        bits.append(f"Comment velocity {c['comment_vph_z']}sd above the field (provokes discussion).")
    if (c.get("convergence_size") or 0) >= 3:
        bits.append(f"{c['convergence_size']} competitors hitting '{c.get('cluster_label')}' inside 48h.")
    if (c.get("calendar_boost") or 0) >= 0.5:
        bits.append(f"Matches the active '{c.get('calendar_phase')}' phase.")
    if c.get("demand_keyword") and (c.get("demand_gap_score") or 0) >= 55:
        bits.append(f"Maps to demand query '{c['demand_keyword']}' (demand score {c['demand_gap_score']}).")
    return " ".join(bits) or "Ranks on views-per-hour within today's set."


def fallback_strategist_take(c: dict, cfg: dict) -> str:
    fmt = c.get("format")
    lang = c.get("lang", "mix")
    rcfg = cfg["report"]
    medium = rcfg["self_channel_eng_name"] if lang == "eng" else rcfg["self_channel_fallback_name"]
    section = ""
    cl = (c.get("cluster_label") or "").lower()
    for route in rcfg.get("section_routing", []):
        if any(k in cl for k in route.get("hints", [])):
            section = route["label"]
            break
    fmt_sugg = {"short": "60s Short", "longform": "8-12 min longform",
                "livestream": "scheduled livestream", "post": "poll or text post"}.get(fmt, "video")
    rel = c.get("relation")
    framing = "benchmark idea, not the lesson" if rel == "indirect" else "direct head-to-head"
    sec_txt = f" Route to {section}." if section else ""
    return f"Make a {fmt_sugg} on the {medium} ({framing}).{sec_txt}"


def enrich(c: dict, narratives: dict, cfg: dict) -> None:
    key = c.get("video_id") or c.get("post_url")
    n = narratives.get(key, {}) if narratives else {}
    c["why"] = n.get("why") or c.get("why") or fallback_why(c)
    c["strategist_take"] = n.get("strategist_take") or c.get("strategist_take") or fallback_strategist_take(c, cfg)
    c["make_call"] = n.get("make_call") or make_this_call(c, cfg)
    if n.get("thumbnail_read"):  # session-authored native thumbnail read
        c["thumbnail_read"] = n["thumbnail_read"]
    if n.get("audience_read"):  # session-authored bullets from mined comments
        c["audience_read"] = n["audience_read"]


# --------------------------------------------------------------------------- #
# Entry rendering
# --------------------------------------------------------------------------- #
def render_entry(rank: int, c: dict, cfg: dict) -> str:
    L = []
    title = (c.get("title") or "").replace("\n", " ").strip()
    L.append(f"[{rank}] {c.get('format','?').upper()} | {title}")
    L.append(f"    Channel: {channel_line(c)}")
    if c.get("kind") == "video":
        out = c.get("outlier")
        out_s = f"{out}x ({c.get('outlier_source')})" if out is not None else "n/a"
        L.append(f"    Posted: {c.get('published_ist','?')} ({fmt_hours(c.get('hours_since'))}) "
                 f"| Views {fmt_int(c.get('views',0))} | VPH {fmt_int(round(c.get('vph',0)))} | Outlier {out_s}")
        L.append(f"    Engagement: {fmt_int(c.get('likes',0))} likes, {fmt_int(c.get('comments',0))} comments, "
                 f"{c.get('comment_vph',0):.1f} comments/hr | eng-rate {c.get('eng_rate',0)*100:.1f}%")
    else:
        L.append(f"    Posted: {c.get('published_ist','?')} ({fmt_hours(c.get('hours_since'))}) "
                 f"| type {c.get('post_type','text')} | {fmt_int(c.get('likes',0))} likes")
        if c.get("poll_options"):
            L.append("    Poll options: " + " | ".join(c["poll_options"]))
    L.append(f"    Flags: {', '.join(c.get('flags',[])) or 'none'} | OppScore {c.get('opportunity_score',0)}")
    L.append(f"    Link: {c.get('link','')}")
    if c.get("kind") == "video":
        L.append(f"    Thumbnail: {c.get('thumbnail_read') or 'n/a'}")
    L.append(f"    Why: {c.get('why','')}")
    L.append(f"    {cfg['report']['take_label']}: {c.get('strategist_take','')}")
    if c.get("audience_read"):
        L.append(f"    Audience read ({c.get('comments_mined', '?')} comments mined):")
        for bullet in c["audience_read"][:5]:
            L.append(f"      - {bullet}")
    return "\n".join(L)


def _section(title: str, items: list[dict], cfg: dict) -> str:
    lo, hi = cfg["report"]["section_min"], cfg["report"]["section_max"]
    out = [f"\n{SUB}\n{title}\n{SUB}"]
    if not items:
        out.append("  (none this run)")
        return "\n".join(out)
    for i, c in enumerate(items[:hi], 1):
        out.append(render_entry(i, c, cfg))
        out.append("")
    if len(items) < lo:
        out.append(f"  (only {len(items)} qualified; field was thin in this format)")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Daily report
# --------------------------------------------------------------------------- #
def build_daily_report(scored: list[dict], meta: dict, cfg: dict, run_info: dict,
                       demand_section: list[dict], narratives: dict | None = None) -> str:
    narratives = narratives or common.read_json(common.cache_path("narratives.json"), {}) or {}
    date = run_info["date"]
    videos = [c for c in scored if c.get("kind") == "video"]
    posts = [c for c in scored if c.get("kind") == "post"]
    rankable = [c for c in scored if c.get("relation") != "self"]
    for c in scored:
        enrich(c, narratives, cfg)

    A = [c for c in videos if c["format"] == "longform" and c["relation"] != "self"]
    B = [c for c in videos if c["format"] == "short" and c["relation"] != "self"]
    C = [c for c in videos if c["format"] == "livestream" and c["relation"] != "self"]
    D = [c for c in posts if c["relation"] != "self"]

    top = sorted(rankable, key=lambda c: c["opportunity_score"], reverse=True)[: cfg["report"]["summary_max_picks"]]
    top_title = (top[0]["title"] if top else "no candidates")[:80]

    out = []
    out.append(f"{cfg['report']['brand_header_daily']}  -  {date}  (lookback 24h, 48h grace)")
    out.append(f"Generated {common.to_ist_str(common.now_utc())}.")
    out.append(f"Sources: YouTube Data API live ({run_info.get('yt_units','?')} units); "
               f"vidIQ {run_info.get('vidiq_status','not run')}; "
               f"community {run_info.get('community_status','not run')}; "
               f"thumbnails {run_info.get('thumb_source','n/a')}; "
               f"clustering {meta.get('cluster_method','?')}.")
    out.append("")
    if run_info.get("run_stats"):
        out.append(build_preface(run_info["run_stats"], "daily", cfg))
        out.append("")
    out.append(SEP)
    out.append("PAGE 1  -  TODAY'S TOP PICKS  (the only page you must read)")
    out.append(SEP)
    if not top:
        out.append("No qualifying candidates in the window. See source notes above.")
    for i, c in enumerate(top, 1):
        out.append(f"\n{i}. [{c['format'].upper()}] {c['make_call']}")
        out.append(f"   Title: {(c.get('title') or '').strip()}")
        out.append(f"   {channel_line(c)}")
        if c.get("kind") == "video":
            out.append(f"   VPH {fmt_int(round(c.get('vph',0)))} | Outlier {c.get('outlier','n/a')}x "
                       f"| Flags: {', '.join(c.get('flags',[])) or 'none'}")
        else:
            out.append(f"   Post type {c.get('post_type','text')} | Flags: {', '.join(c.get('flags',[])) or 'none'}")
        out.append(f"   Link: {c.get('link','')}")
        out.append(f"   {cfg['report']['take_label']}: {c.get('strategist_take','')}")

    if demand_section:
        d0 = demand_section[0]
        out.append("\nSTRONGEST DEMAND OPPORTUNITY:")
        out.append(f'   "{d0["keyword"]}"  gap {d0["gap_score"]}'
                   + (f' | vol {d0["volume"]:.0f} comp {d0["competition"]:.0f}' if d0["has_vidiq"] else " (vidIQ not run; computed from supply)")
                   + f' | supply: {d0["supply_matches"]} recent matches'
                   + (", stale/thin" if d0["stale_or_thin"] else ""))

    out.append("\nTODAY'S READ:")
    out.append(f"   {_todays_read(scored, meta, cfg)}")

    # Full sections
    out.append("\n" + SEP)
    out.append("FULL SECTIONS (ranked; indirect competitors shown in full)")
    out.append(SEP)
    out.append(_section("SECTION A  -  LONGFORM", A, cfg))
    out.append(_section("SECTION B  -  SHORTS", B, cfg))
    out.append(_section("SECTION C  -  LIVESTREAMS (live / concluded 24h / upcoming)", C, cfg))
    out.append(_section("SECTION D  -  COMMUNITY POSTS", D, cfg))
    out.append(_demand_section_text(demand_section, cfg))

    # Appendix
    out.append("\n" + SEP)
    out.append("APPENDIX  -  FULL RANKED MACHINE-READABLE BLOCK")
    out.append(SEP)
    for c in sorted(scored, key=lambda x: x.get("opportunity_score", 0), reverse=True):
        out.append(_appendix_row(c))
    return "\n".join(out)


def _todays_read(scored, meta, cfg) -> str:
    videos = [c for c in scored if c.get("kind") == "video" and c["relation"] != "self"]
    conv = {}
    for v in videos:
        if (v.get("convergence_size") or 0) >= cfg["convergence"]["min_cluster_size"]:
            conv[v.get("cluster_label")] = v["convergence_size"]
    parts = []
    if conv:
        top_conv = max(conv.items(), key=lambda x: x[1])
        parts.append(f"Convergence: {top_conv[1]} competitors on '{top_conv[0]}' in 48h.")
    else:
        parts.append("No 3+ competitor convergence today.")
    if meta.get("active_phase_label"):
        parts.append(f"Calendar: live phase is '{meta['active_phase_label']}' - boost foundation/start-now hooks.")
    return " ".join(parts)


def _demand_section_text(demand_section, cfg) -> str:
    out = [f"\n{SUB}\nSECTION E  -  KEYWORD & DEMAND OPPORTUNITIES\n{SUB}"]
    if not demand_section:
        out.append("  (no keyword data this run)")
        return "\n".join(out)
    for i, d in enumerate(demand_section[: cfg["report"]["section_max"]], 1):
        meta = (f"vol {d['volume']:.0f} | comp {d['competition']:.0f} | score {d['overall_score']:.0f}"
                if d["has_vidiq"] else "vidIQ not run (computed from own supply)")
        supply = (f"{d['supply_matches']} recent matches"
                  + (f", newest {fmt_hours(d['supply_newest_hours'])}" if d["supply_newest_hours"] is not None else "")
                  + (", STALE/THIN" if d["stale_or_thin"] else ""))
        out.append(f"[{i}] \"{d['keyword']}\"  gap {d['gap_score']}")
        out.append(f"    Demand: {meta}")
        out.append(f"    Supply: {supply}")
        out.append("")
    return "\n".join(out)


def _appendix_row(c: dict) -> str:
    return ("  " + " | ".join([
        f"opp={c.get('opportunity_score',0)}",
        f"fmt={c.get('format')}",
        f"rel={c.get('relation')}",
        f"ch={c.get('channel_name')}",
        f"vph={round(c.get('vph',0) or 0,1)}",
        f"out={c.get('outlier')}",
        f"cvph={c.get('comment_vph',0)}",
        f"engrate={c.get('eng_rate',0)}",
        f"flags={'/'.join(c.get('flags',[])) or '-'}",
        f"id={c.get('video_id') or c.get('post_url')}",
        f"link={c.get('link')}",
    ]))


# --------------------------------------------------------------------------- #
# Weekly report
# --------------------------------------------------------------------------- #
def build_weekly_report(scored: list[dict], meta: dict, cfg: dict, run_info: dict,
                        demand_section: list[dict], weekly_extras: dict,
                        narratives: dict | None = None) -> str:
    narratives = narratives or common.read_json(common.cache_path("narratives.json"), {}) or {}
    date = run_info["date"]
    for c in scored:
        enrich(c, narratives, cfg)
    rankable = [c for c in scored if c.get("relation") != "self"]
    durable = weekly_extras.get("durable", [])[: cfg["report"]["summary_max_picks"]]

    out = []
    out.append(f"{cfg['report']['brand_header_weekly']}  -  week of {date}  (lookback 7 days)")
    out.append(f"Generated {common.to_ist_str(common.now_utc())}.")
    out.append(f"Sources: YouTube Data API live ({run_info.get('yt_units','?')} units); "
               f"vidIQ {run_info.get('vidiq_status','not run')}; "
               f"history rows {weekly_extras.get('history_rows',0)}; "
               f"clustering {meta.get('cluster_method','?')}.")
    out.append("")
    if run_info.get("run_stats"):
        out.append(build_preface(run_info["run_stats"], "weekly", cfg))
        out.append("")
    out.append(SEP)
    out.append("PAGE 1  -  WEEKLY SUMMARY")
    out.append(SEP)
    out.append("\nDURABLE WINNERS (sustained, not one-day spikes):")
    if not durable:
        out.append("  (history thin; durable detection strengthens as snapshots accrue)")
    for i, c in enumerate(durable, 1):
        out.append(f"  {i}. [{c['format'].upper()}] {(c.get('title') or '').strip()[:80]}")
        out.append(f"     {channel_line(c)} | VPH {fmt_int(round(c.get('vph',0)))} | {fmt_hours(c.get('hours_since'))}")
        out.append(f"     {cfg['report']['take_label']}: {c.get('strategist_take','')}")

    out.append("\nDOMINANT TOPICS & PACKAGING PATTERNS:")
    for p in weekly_extras.get("patterns", [])[:6]:
        out.append(f"  - {p}")
    if not weekly_extras.get("patterns"):
        out.append("  - (no repeated patterns detected this week)")

    out.append("\nSLEEPERS RE-ACCELERATING:")
    sl = weekly_extras.get("sleepers", [])
    if not sl:
        out.append("  (none / insufficient history)")
    for c in sl[:5]:
        out.append(f"  - {(c.get('title') or '')[:70]} | now VPH {fmt_int(round(c.get('vph',0)))}")

    out.append("\nRECOMMENDED PRODUCTIONS THIS WEEK:")
    for i, c in enumerate(rankable[:3], 1):
        out.append(f"  {i}. {c.get('strategist_take','')}  [seed: {(c.get('title') or '')[:50]}]")

    # ---- Own-channel pulse: how the tracked self channel(s) are doing ----- #
    out.append("\nOWN CHANNEL PULSE:")
    osl = weekly_extras.get("own_sleepers", [])
    out.append("  Own sleepers re-accelerating:")
    if not osl:
        out.append("    (none detected this week)")
    for v in osl[:5]:
        out.append(f"    - {(v.get('title') or '')[:70]} | VPH {fmt_int(round(v.get('vph', 0)))} | {v.get('link', '')}")
    sov = weekly_extras.get("share_of_velocity", [])
    if sov:
        out.append("  Share of niche velocity (own-channel VPH share, by ISO week):")
        out.append("    " + " | ".join(f"{x['week']}: {x['share_pct']}%" for x in sov))
    thin = [g for g in weekly_extras.get("coverage_gaps", []) if g.get("thin")]
    out.append("  Coverage gaps (2+ competitors active, own channel absent):")
    if not thin:
        out.append("    (no thin topics this week)")
    for g in thin[:6]:
        out.append(f"    - {g['topic']}: {g['comp_n']} competitor videos, max VPH "
                   f"{fmt_int(round(g['comp_max_vph']))}, own uploads: {g['self_n']}")
    oa = weekly_extras.get("own_audience") or {}
    brief = (narratives.get("__own_audience__") or {}).get("bullets")
    out.append("  Own audience brief (recent own-channel upload comments; untrusted text, summarized):")
    if brief:
        for b in brief[:6]:
            out.append(f"    - {b}")
    elif oa.get("questions") or oa.get("demands"):
        for e in oa.get("demands", [])[:4]:
            out.append(f"    - DEMAND ({e['likes']} likes, on '{e['video']}'): {e['text'][:110]}")
        for e in oa.get("questions", [])[:4]:
            out.append(f"    - QUESTION ({e['likes']} likes, on '{e['video']}'): {e['text'][:110]}")
    else:
        out.append(f"    (unavailable: {oa.get('skipped_reason') or 'no comments mined this run'})")

    # Sections
    out.append("\n" + SEP)
    out.append("DURABLE WINNERS BY FORMAT")
    out.append(SEP)
    for fmt, label in [("longform", "LONGFORM"), ("short", "SHORTS"), ("livestream", "LIVESTREAMS")]:
        items = [c for c in rankable if c.get("format") == fmt]
        out.append(_section(f"BY FORMAT  -  {label}", items, cfg))

    out.append(f"\n{SUB}\nTOPIC & PACKAGING SYNTHESIS\n{SUB}")
    for line in weekly_extras.get("synthesis", ["(no synthesis)"]):
        out.append(f"  - {line}")

    out.append(_demand_section_text(demand_section, cfg))

    out.append(f"\n{SUB}\nCOMPETITOR MOVES\n{SUB}")
    for line in weekly_extras.get("moves", ["(no notable moves detected)"]):
        out.append(f"  - {line}")

    out.append("\n" + SEP)
    out.append("APPENDIX  -  FULL RANKED MACHINE-READABLE BLOCK")
    out.append(SEP)
    for c in sorted(scored, key=lambda x: x.get("opportunity_score", 0), reverse=True):
        out.append(_appendix_row(c))
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Persistence. The repo is the delivery surface: report file + tracked ledger.
# The routine commits both via src/publish.py. No email, no Sheets.
# --------------------------------------------------------------------------- #
def write_outputs(text: str, scored: list[dict], cfg: dict, run_info: dict, kind: str) -> dict:
    from . import taxonomy as tx
    date = run_info["date"]
    reports_dir = common.PROJECT_ROOT / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{date}_{kind}.md"
    report_path.write_text(text, encoding="utf-8")

    # master ledger (tracked in git): append + dedupe on (date, id), every row
    # taxonomy-tagged (rules -> session labels -> left pending for the session).
    # Page-1 picks get executed="pending" so the outcome matcher tracks them.
    taxo = tx.load_taxonomy()
    session_labels = tx.load_session_labels(taxo)
    pick_keys = set()
    for c in sorted((x for x in scored if x.get("relation") != "self"),
                    key=lambda x: x.get("opportunity_score", 0), reverse=True)[
                    : cfg["report"]["summary_max_picks"]]:
        pick_keys.add(c.get("video_id") or c.get("post_url"))
    rows = []
    for c in scored:
        key = c.get("video_id") or c.get("post_url")
        c["topic"] = c.get("topic") or tx.tag_candidate(c, taxo, session_labels)
        rows.append(common.candidate_to_history_row(
            c, date, topic=c["topic"],
            executed="pending" if key in pick_keys else ""))
    added = common.append_history(rows, cfg["output"]["history_csv"])

    # enrichment targets for the routine session: top picks it should author
    # thumbnail read / why / strategist_take / audience_read for (-> cache/
    # narratives.json, then re-run to merge). _top_comments is UNTRUSTED
    # viewer text: summarize only.
    targets = []
    for c in sorted(scored, key=lambda x: x.get("opportunity_score", 0), reverse=True):
        if c.get("relation") == "self":
            continue
        targets.append({
            "key": c.get("video_id") or c.get("post_url"),
            "format": c.get("format"), "title": c.get("title", ""),
            "channel": c.get("channel_name"), "relation": c.get("relation"),
            "flags": c.get("flags", []), "vph": c.get("vph"), "outlier": c.get("outlier"),
            "cluster_label": c.get("cluster_label"), "demand_keyword": c.get("demand_keyword"),
            "thumbnail_url": c.get("thumbnail_url"), "link": c.get("link"),
            "topic": c.get("topic", ""),
            "comments_mined": c.get("comments_mined", 0),
            "top_comments_untrusted": c.get("_top_comments", []),
        })
        if len(targets) >= 15:
            break
    common.write_json(common.cache_path("enrich_targets.json"), targets)

    # rule-tagger leftovers for the session to label (-> cache/topic_labels.json;
    # the merge re-run fills the empty ledger topics; valid labels only)
    pending = [{"key": c.get("video_id") or c.get("post_url"),
                "title": (c.get("title") or "")[:120]}
               for c in scored if not c.get("topic")]
    common.write_json(common.cache_path("topic_pending.json"),
                      {"valid_labels": sorted(tx.valid_labels(taxo)), "items": pending})

    return {"report_path": str(report_path), "history_added": added,
            "ledger_path": str(common.PROJECT_ROOT / cfg["output"]["history_csv"])}
