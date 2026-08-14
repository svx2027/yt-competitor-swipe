"""YouTube Data API v3 layer: resolve channels, pull recent uploads, classify
content type, compute VPH and engagement velocity. Quota-disciplined.

Quota costs (units): channels.list=1, playlistItems.list=1, videos.list=1,
search.list=100. The client tracks cumulative units and refuses search.list
once the per-run budget would be exceeded.
"""
from __future__ import annotations

import csv
import re
import sys
import time
from datetime import timedelta

import requests

from . import common

API = "https://www.googleapis.com/youtube/v3"
_DUR_RE = re.compile(
    r"P(?:(?P<d>\d+)D)?T?(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?"
)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# Strong niche signals for the active vertical, loaded from config.yaml's
# niche.tokens (see common.load_config -> vertical-resolved config). A
# keyword-discovery video must contain at least one of these (in title/
# description/tags) to survive; this rejects off-niche discovery noise -
# literal word collisions, unrelated content that happens to share a token,
# etc. The active niche's token list lives in config.yaml, unchanged across
# verticals.
def is_niche_video(item: dict, niche_tokens) -> bool:
    snip = item.get("snippet", {})
    hay = " ".join([
        snip.get("title", ""),
        snip.get("description", "")[:400],
        " ".join(snip.get("tags", []) or []),
    ]).lower()
    return any(tok in hay for tok in niche_tokens)


def parse_duration(iso: str) -> int:
    """ISO-8601 duration (e.g. PT1M5S) -> seconds. 0 if unparseable/empty."""
    if not iso:
        return 0
    m = _DUR_RE.fullmatch(iso)
    if not m:
        return 0
    d, h, mi, s = (common.safe_int(m.group(k)) for k in ("d", "h", "m", "s"))
    return d * 86400 + h * 3600 + mi * 60 + s


class YouTubeClient:
    def __init__(self, api_key: str, unit_budget: int = 9000):
        self.key = api_key
        self.units = 0
        self.budget = unit_budget
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict, cost: int) -> dict:
        if self.units + cost > self.budget:
            raise RuntimeError(
                f"YouTube quota budget exceeded ({self.units}+{cost} > {self.budget})"
            )
        params = dict(params, key=self.key)
        last_err = None
        for attempt in range(3):
            r = self.session.get(f"{API}/{endpoint}", params=params, timeout=45)
            if r.status_code == 200:
                self.units += cost
                return r.json()
            if r.status_code in (403, 429) and "quota" in r.text.lower():
                raise RuntimeError(f"YouTube quota error: {r.text[:200]}")
            if r.status_code >= 500:
                last_err = f"YouTube {endpoint} HTTP {r.status_code}: {r.text[:200]}"
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            # 4xx other than quota: surface immediately, no retry
            raise RuntimeError(f"YouTube {endpoint} HTTP {r.status_code}: {r.text[:200]}")
        raise RuntimeError(last_err or f"YouTube {endpoint} failed after retries")

    # ---- channel resolution ------------------------------------------------ #
    def resolve_handle(self, handle: str) -> dict | None:
        """Resolve an @handle (or bare name) to channel snippet+stats+uploads."""
        h = handle.lstrip("@")
        # 1) forHandle (cheapest, exact)
        for variant in (f"@{h}", h):
            try:
                data = self._get(
                    "channels",
                    {"part": "snippet,statistics,contentDetails", "forHandle": variant},
                    1,
                )
                if data.get("items"):
                    return data["items"][0]
            except RuntimeError:
                pass
        # 2) legacy forUsername
        try:
            data = self._get(
                "channels",
                {"part": "snippet,statistics,contentDetails", "forUsername": h},
                1,
            )
            if data.get("items"):
                return data["items"][0]
        except RuntimeError:
            pass
        # 3) search fallback (100 units) - last resort
        try:
            s = self._get(
                "search",
                {"part": "snippet", "q": handle, "type": "channel", "maxResults": 1},
                100,
            )
            items = s.get("items", [])
            if items:
                cid = items[0]["snippet"]["channelId"]
                return self.get_channels([cid]).get(cid)
        except RuntimeError:
            pass
        return None

    def get_channels(self, channel_ids: list[str]) -> dict:
        """Batch channels.list by id -> {channel_id: item}."""
        out = {}
        for i in range(0, len(channel_ids), 50):
            batch = channel_ids[i : i + 50]
            data = self._get(
                "channels",
                {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)},
                1,
            )
            for it in data.get("items", []):
                out[it["id"]] = it
        return out

    # ---- uploads -> recent videos ------------------------------------------ #
    def recent_video_ids(self, uploads_playlist: str, after_iso: str, max_items: int) -> list[str]:
        ids, page, pages = [], None, 0
        cutoff = common.parse_iso(after_iso)
        while pages < 3 and len(ids) < max_items:
            params = {"part": "contentDetails", "playlistId": uploads_playlist, "maxResults": 50}
            if page:
                params["pageToken"] = page
            data = self._get("playlistItems", params, 1)
            stop = False
            for it in data.get("items", []):
                cd = it.get("contentDetails", {})
                vid = cd.get("videoId")
                pub = cd.get("videoPublishedAt")
                if not vid:
                    continue
                if pub and common.parse_iso(pub) < cutoff:
                    stop = True
                    continue
                ids.append(vid)
            page = data.get("nextPageToken")
            pages += 1
            if stop or not page:
                break
        return ids[: max_items * 3]  # margin; videos.list will re-filter

    def hydrate_videos(self, video_ids: list[str]) -> dict:
        """videos.list batched -> {video_id: item with snippet/stats/details/live}."""
        out = {}
        uniq = list(dict.fromkeys(video_ids))
        for i in range(0, len(uniq), 50):
            batch = uniq[i : i + 50]
            data = self._get(
                "videos",
                {
                    "part": "snippet,statistics,contentDetails,liveStreamingDetails,status",
                    "id": ",".join(batch),
                },
                1,
            )
            for it in data.get("items", []):
                out[it["id"]] = it
        return out

    def comment_threads(self, video_id: str, max_results: int = 100,
                        pages: int = 2, order: str = "relevance") -> list[dict]:
        """Top-level comments for a video (1 unit/page). Returns [] when the
        video has comments disabled instead of raising."""
        out, token = [], None
        for _ in range(max(pages, 1)):
            params = {
                "part": "snippet", "videoId": video_id, "order": order,
                "maxResults": min(max_results, 100), "textFormat": "plainText",
            }
            if token:
                params["pageToken"] = token
            try:
                data = self._get("commentThreads", params, 1)
            except RuntimeError as e:
                if "commentsDisabled" in str(e):
                    return out
                raise  # any other 4xx/quota error should surface, not be read as "no comments"
            for it in data.get("items", []):
                top = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                text = (top.get("textDisplay") or "").replace("\r", " ").replace("\n", " ").strip()
                if not text:
                    continue
                out.append({
                    "text": text[:500],
                    "likes": common.safe_int(top.get("likeCount")),
                    "author": (top.get("authorDisplayName") or "")[:60],
                    "replies": common.safe_int(it.get("snippet", {}).get("totalReplyCount")),
                    "published_at": top.get("publishedAt", ""),
                })
            token = data.get("nextPageToken")
            if not token:
                break
        return out

    def search_keyword(self, query: str, after_iso: str, region: str, lang: str,
                       max_results: int, category_id: str = "27") -> list[str]:
        data = self._get(
            "search",
            {
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "viewCount",
                "publishedAfter": after_iso,
                "maxResults": min(max_results, 50),
                "regionCode": region,
                "relevanceLanguage": lang,
                # Default "27" = Education; config-driven so a different
                # content vertical isn't silently tied to an assumption that
                # doesn't fit it.
                "videoCategoryId": category_id,
            },
            100,
        )
        return [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def is_short_redirect(video_id: str) -> bool:
    """For 61-180s videos: GET /shorts/<id>; 200 => short, redirect => not."""
    try:
        r = requests.get(
            f"https://www.youtube.com/shorts/{video_id}",
            allow_redirects=False,
            timeout=8,
            headers={"User-Agent": _UA},
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


def live_status_of(item: dict, recently_concluded_h: int) -> str:
    snip = item.get("snippet", {})
    lbc = snip.get("liveBroadcastContent", "none")
    lsd = item.get("liveStreamingDetails")
    if lbc == "live":
        return "live"
    if lbc == "upcoming":
        return "upcoming"
    if lsd and lsd.get("actualEndTime"):
        ended = common.parse_iso(lsd["actualEndTime"])
        if common.hours_since(ended) <= recently_concluded_h:
            return "concluded"
        return "concluded_old"
    if lsd:  # has live details but no end -> treat as concluded/none
        return "concluded_old"
    return "none"


def classify(item: dict, duration_sec: int, live_status: str, cfg: dict) -> str:
    cc = cfg["classification"]
    if live_status in ("live", "upcoming", "concluded"):
        return "livestream"
    if live_status == "concluded_old":
        return "longform"  # an old stream behaving like a VOD
    if duration_sec and duration_sec <= cc["short_max_seconds"]:
        return "short"
    if duration_sec and duration_sec <= cc["short_redirect_max_seconds"]:
        if is_short_redirect(item["id"]):
            return "short"
    return "longform"


# --------------------------------------------------------------------------- #
# Candidate builder
# --------------------------------------------------------------------------- #
def build_candidate(item: dict, comp_row: dict, cfg: dict) -> dict:
    vid = item["id"]
    snip = item.get("snippet", {})
    stats = item.get("statistics", {})
    cd = item.get("contentDetails", {})
    pub = common.parse_iso(snip.get("publishedAt"))
    hrs = common.hours_since(pub) if pub else 0.0
    views = common.safe_int(stats.get("viewCount"))
    likes = common.safe_int(stats.get("likeCount"))
    comments = common.safe_int(stats.get("commentCount"))
    dur = parse_duration(cd.get("duration", ""))
    live = live_status_of(item, cfg["classification"]["recently_concluded_live_hours"])
    fmt = classify(item, dur, live, cfg)
    denom = max(hrs, 1.0)  # avoid div-by-zero for fresh uploads; floor at 1h
    return {
        "kind": "video",
        "format": fmt,
        "video_id": vid,
        "post_url": None,
        "link": common.watch_url(vid),
        "channel_id": comp_row.get("channel_id") or snip.get("channelId", ""),
        "channel_name": comp_row.get("name") or snip.get("channelTitle", ""),
        "relation": comp_row.get("relation", "direct"),
        "channel_type": comp_row.get("type", ""),
        "channel_subs": common.safe_int(comp_row.get("subs")),
        "lang": comp_row.get("lang", "mix"),
        "title": snip.get("title", ""),
        "published_at": snip.get("publishedAt", ""),
        "published_ist": common.to_ist_str(pub),
        "hours_since": round(hrs, 2),
        "views": views,
        "likes": likes,
        "comments": comments,
        "duration_sec": dur,
        "vph": round(views / denom, 2),
        "like_vph": round(likes / denom, 3),
        "comment_vph": round(comments / denom, 3),
        "eng_rate": round((likes + comments) / views, 5) if views else 0.0,
        "live_status": live,
        "thumbnail_url": common.thumb_url(vid),
        "thumbnail_read": None,
        "flags": [],
        "source": comp_row.get("_source", "channel"),
    }


# --------------------------------------------------------------------------- #
# Channel resolution (writes channel_id + subs back into competitors.csv)
# --------------------------------------------------------------------------- #
def resolve_all_channels(client: YouTubeClient, force: bool = False) -> tuple[list[dict], dict]:
    rows = common.load_competitors()
    meta_cache = {}
    need_ids = []
    for r in rows:
        if not r.get("channel_id") or force:
            if not r["handle_or_id"].startswith("@") and r["handle_or_id"].startswith("UC"):
                r["channel_id"] = r["handle_or_id"]
            else:
                item = client.resolve_handle(r["handle_or_id"])
                if item:
                    r["channel_id"] = item["id"]
                    meta_cache[item["id"]] = item
                else:
                    print(f"  ! could not resolve {r['name']} ({r['handle_or_id']})", file=sys.stderr)
        if r.get("channel_id"):
            need_ids.append(r["channel_id"])

    # fetch meta (uploads playlist + subs) for any channel we don't have yet
    missing = [cid for cid in need_ids if cid and cid not in meta_cache]
    if missing:
        meta_cache.update(client.get_channels(missing))

    # write subs + channel_id back into rows and persist
    for r in rows:
        cid = r.get("channel_id")
        if cid and cid in meta_cache:
            stats = meta_cache[cid].get("statistics", {})
            r["subs"] = stats.get("subscriberCount", r.get("subs", ""))
            r["resolved_at"] = common.now_utc().strftime("%Y-%m-%d")
    _write_competitors(rows)

    # also persist a quick channel_id + uploads-playlist cache
    upl = {}
    for cid, it in meta_cache.items():
        upl[cid] = {
            "title": it.get("snippet", {}).get("title", ""),
            "uploads": it.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
            "subs": common.safe_int(it.get("statistics", {}).get("subscriberCount")),
        }
    common.write_json(common.cache_path("channel_ids.json"), upl)
    return rows, meta_cache


def _write_competitors(rows: list[dict]) -> None:
    """Rewrites competitors.csv. Header-driven like the ledger writers in
    common.py: the base columns come first, but any extra column an operator
    hand-added to the CSV (a note, a priority flag, anything) is preserved
    rather than silently dropped on the next resolve."""
    base_fields = ["name", "handle_or_id", "relation", "type", "cadence", "lang",
                   "channel_id", "subs", "resolved_at"]
    extra_fields = []
    for r in rows:
        for k in r.keys():
            if k not in base_fields and k not in extra_fields:
                extra_fields.append(k)
    fields = base_fields + extra_fields
    path = common.competitors_path()
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def ensure_uploads_meta(client: YouTubeClient, rows: list[dict], meta_cache: dict) -> dict:
    """Guarantee every channel_id has uploads-playlist + subs in cache."""
    cache = common.read_json(common.cache_path("channel_ids.json"), {}) or {}
    ids = [r["channel_id"] for r in rows if r.get("channel_id")]
    missing = [cid for cid in ids if cid not in cache or not cache[cid].get("uploads")]
    missing = [cid for cid in missing if cid not in meta_cache]
    if missing:
        meta_cache.update(client.get_channels(missing))
    for cid, it in meta_cache.items():
        cache[cid] = {
            "title": it.get("snippet", {}).get("title", ""),
            "uploads": it.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
            "subs": common.safe_int(it.get("statistics", {}).get("subscriberCount")),
        }
    common.write_json(common.cache_path("channel_ids.json"), cache)
    return cache


# --------------------------------------------------------------------------- #
# Main pull
# --------------------------------------------------------------------------- #
def build_baselines(client: YouTubeClient, rows: list[dict], cfg: dict, force: bool = False) -> dict:
    """Per-channel outlier baseline: median lifetime VPH over the channel's last
    N uploads. Rough proxy for 'expected pace' (vidIQ is preferred when present);
    cached to cache/baselines.json and refreshed every baseline_refresh_days.
    """
    path = common.cache_path("baselines.json")
    cache = common.read_json(path, {}) or {}
    built = common.parse_iso(cache.get("_built_at", "")) if cache.get("_built_at") else None
    if built and not force:
        if common.hours_since(built) < cfg["youtube"]["baseline_refresh_days"] * 24:
            return cache  # still fresh

    chan_cache = common.read_json(common.cache_path("channel_ids.json"), {}) or {}
    n_items = cfg["youtube"]["baseline_items"]
    out = {"_built_at": common.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")}
    for r in rows:
        cid = r.get("channel_id")
        uploads = (chan_cache.get(cid) or {}).get("uploads")
        if not cid or not uploads:
            continue
        if client.units + 3 > client.budget:
            break
        try:
            # recent uploads regardless of date (wide window)
            far = (common.now_utc() - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
            ids = client.recent_video_ids(uploads, far, n_items)[:n_items]
            items = client.hydrate_videos(ids)
        except RuntimeError:
            continue
        vphs = []
        for it in items.values():
            pub = common.parse_iso(it.get("snippet", {}).get("publishedAt"))
            views = common.safe_int(it.get("statistics", {}).get("viewCount"))
            if not pub or views <= 0:
                continue
            hrs = max(common.hours_since(pub), 1.0)
            vphs.append(views / hrs)
        if vphs:
            vphs.sort()
            out[cid] = {"median_vph": round(vphs[len(vphs) // 2], 3), "n": len(vphs)}
    common.write_json(path, out)
    return out


def pull_candidates(client: YouTubeClient, rows: list[dict], cfg: dict,
                    lookback_hours: float, max_items: int,
                    include_self: bool = True, stats: dict | None = None) -> list[dict]:
    stats = stats if stats is not None else {}
    after_iso = (common.now_utc() - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    cache = common.read_json(common.cache_path("channel_ids.json"), {}) or {}
    by_cid = {r["channel_id"]: r for r in rows if r.get("channel_id")}
    stats["channels_scanned"] = len(by_cid)

    # 1) collect recent video IDs per channel
    all_ids, id_to_row = [], {}
    for cid, r in by_cid.items():
        if r.get("relation") == "self" and not include_self:
            continue
        uploads = (cache.get(cid) or {}).get("uploads")
        if not uploads:
            continue
        try:
            vids = client.recent_video_ids(uploads, after_iso, max_items)
        except RuntimeError as e:
            print(f"  ! {r['name']}: {e}", file=sys.stderr)
            continue
        for v in vids:
            all_ids.append(v)
            id_to_row[v] = r

    stats["videos_from_channels"] = len(all_ids)

    # 2) keyword-discovery pass (search.list) - bounded by quota budget
    discovery_ids = {}
    stats["keywords_searched"] = 0
    if cfg["youtube"].get("keyword_search_enabled"):
        kws = common.load_keywords()[: cfg["youtube"]["keyword_search_max_keywords"]]
        for kw in kws:
            if client.units + 100 > client.budget:
                print("  ! quota budget reached; stopping keyword discovery", file=sys.stderr)
                break
            try:
                vids = client.search_keyword(
                    kw, after_iso, cfg["youtube"]["region_code"],
                    cfg["youtube"]["relevance_language"],
                    cfg["youtube"]["keyword_search_results"],
                    category_id=cfg["youtube"].get("video_category_id", "27"),
                )
                stats["keywords_searched"] += 1
                for v in vids:
                    discovery_ids[v] = kw
                    if v not in id_to_row:
                        all_ids.append(v)
            except RuntimeError as e:
                print(f"  ! keyword '{kw}': {e}", file=sys.stderr)

    # 3) hydrate everything
    items = client.hydrate_videos(all_ids)

    # 4) build candidates (re-filter by lookback + grace, validate publicity)
    grace = cfg["lookback"]["daily_grace_hours"]
    niche_tokens = cfg["niche"]["tokens"]
    candidates = []
    for vid, item in items.items():
        status = item.get("status", {})
        if status.get("privacyStatus") not in (None, "public"):
            continue  # link must resolve to a public watch URL
        pub = common.parse_iso(item.get("snippet", {}).get("publishedAt"))
        if not pub:
            continue
        age = common.hours_since(pub)
        row = id_to_row.get(vid)
        if row is None:
            # discovery video. If it is actually one of our competitor channels,
            # treat it as trusted; otherwise require it to pass the niche gate.
            chan_id = item.get("snippet", {}).get("channelId", "")
            row = by_cid.get(chan_id)
            if row is None:
                if not is_niche_video(item, niche_tokens):
                    continue  # reject off-niche discovery noise (niche.tokens gate failed)
                row = {
                    "name": item.get("snippet", {}).get("channelTitle", "(discovery)"),
                    "channel_id": chan_id,
                    "relation": "indirect", "type": "creator", "lang": "mix",
                    "subs": "", "_source": f"keyword:{discovery_ids.get(vid,'')}",
                }
            # Deliberately stricter than the direct-pull branch below: a video
            # that only surfaced via keyword search (never appeared in a
            # tracked channel's own upload feed within this run) always uses
            # the tighter `grace` window, even if it turns out to belong to a
            # known channel - keyword discovery is speculative/noisier, so it
            # doesn't inherit the full lookback+grace allowance a direct pull
            # gets.
            if age > grace:
                continue
        else:
            if age > max(lookback_hours, grace):
                continue
        c = build_candidate(item, row, cfg)
        # Only relabel as keyword-sourced when the video wasn't already
        # resolved via a tracked channel's own uploads feed - that trusted
        # path is more authoritative than an incidental keyword-search match.
        if vid in discovery_ids and id_to_row.get(vid) is None:
            c["source"] = f"keyword:{discovery_ids[vid]}"
        candidates.append(c)

    stats["videos_hydrated"] = len(items)
    stats["video_candidates"] = len(candidates)

    # enrich subscriber counts for discovery channels (cheap; report quality)
    disc_cids = {c["channel_id"] for c in candidates
                 if c.get("channel_subs", 0) == 0 and c.get("channel_id")
                 and str(c.get("source", "")).startswith("keyword")}
    if disc_cids:
        try:
            meta = client.get_channels(list(disc_cids))
            for c in candidates:
                m = meta.get(c["channel_id"])
                if m:
                    c["channel_subs"] = common.safe_int(m.get("statistics", {}).get("subscriberCount"))
        except RuntimeError:
            pass

    return candidates
