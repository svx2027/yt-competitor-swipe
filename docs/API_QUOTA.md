# API quota engineering

The YouTube Data API v3 gives every project a fixed 10,000-unit daily quota
(resets at midnight Pacific), shared across every endpoint the project calls.
Tracking dozens of competitor channels a day, on a free-tier quota, means
every call has to earn its cost. This is how the pull layer
(`src/youtube_pull.py`) stays inside budget without silently dropping
channels.

## Unit costs (per the API's published pricing)

| Endpoint | Cost | Used for |
|---|---|---|
| `channels.list` | 1 | Resolving a handle to a channel ID, subs, uploads playlist |
| `playlistItems.list` | 1 | Paging a channel's uploads playlist for recent video IDs |
| `videos.list` | 1 | Batch-hydrating up to 50 video IDs at once (stats, duration, live status) |
| `commentThreads.list` | 1 | One page (up to 100) of top-level comments per video |
| `search.list` | **100** | Keyword-discovery fallback and the last-resort handle-search path |

`search.list` is two orders of magnitude more expensive than everything
else — a naive design that leans on keyword search to find competitor
content would burn the daily budget on a handful of queries. Every other
call in the pull path is deliberately routed around it wherever a cheaper
endpoint gives the same answer.

## Where the budget goes

`YouTubeClient` (`src/youtube_pull.py`) tracks cumulative spent units
(`self.units`) against a configured budget (`config.yaml`'s
`quota.yt_daily_unit_budget`, default **9000** — a hard stop kept under the
real 10,000 cap, not the cap itself, so a run always has headroom rather
than racing the exact limit) and refuses any call that would exceed it
(`_get` raises before making the request). A run spends its budget roughly
in this order:

1. **Channel resolution** (`resolve_handle`) — 1 unit per channel via
   `forHandle`, with a `forUsername` fallback, both 1 unit. Only if both
   fail does it drop to the 100-unit `search.list` fallback, and only for
   channels that still have no resolved ID — a one-time cost per channel,
   not a per-run cost, since resolved IDs are written back to
   `competitors.csv`.
2. **Uploads playlist paging** (`recent_video_ids`) — 1 unit per page (up to
   50 items), capped at 3 pages per channel per run. For a channel with a
   normal upload cadence this is 1 unit; the cap exists so one
   unusually-active channel can't consume the whole run's budget paging
   through its uploads feed.
3. **Video hydration** (`hydrate_videos`) — 1 unit per **batch of 50** video
   IDs, not per video. Every candidate from every channel and every
   discovery match is deduplicated and hydrated in one batched pass at the
   end of collection, so the cost is `ceil(unique_video_count / 50)`
   regardless of how many channels or keywords contributed to that set.
4. **Baselines** (`build_baselines`) — the per-channel outlier baseline
   (median VPH over a channel's last N uploads) is cached to
   `cache/baselines.json` and only rebuilt every
   `youtube.baseline_refresh_days` (default 3), not every run. Inside a
   rebuild it checks remaining budget before each channel
   (`client.units + 3 > client.budget`) and stops early rather than
   partially exhausting the budget mid-pass.
5. **Keyword discovery** (`search_keyword`) — the 100-unit path, and the
   only one used deliberately rather than as a fallback. Bounded on two
   axes in `config.yaml`: `keyword_search_max_keywords` (default 8) caps how
   many queries run at all, and the loop itself re-checks
   `client.units + 100 > client.budget` before every query and stops
   discovery (not the whole run) once the budget would be exceeded — so a
   quota squeeze degrades discovery breadth first, never the channels
   already being tracked directly.
6. **Comments** (`comment_threads`) — 1 unit per page, opt-in per pick
   (`comments.max_picks`, default 8) and gated by its own floor:
   `comments.min_remaining_units` (default 500) skips comment mining
   entirely if the run is already low on budget, rather than spending the
   last of it on comments and leaving the core scan short.

## The degradation ladder

The design principle threaded through all of this: **the core scan and
scoring never gets skipped for quota reasons; everything layered on top of
it degrades gracefully instead.** Concretely, in the order a quota squeeze
actually bites:

1. Keyword discovery stops early (still-tracked channels are unaffected).
2. Comment mining is skipped below the 500-unit floor.
3. Baseline outliers fall back to same-run channel medians
   (`score.py`'s `compute_outliers`: vidIQ score, if present, wins over a
   cached baseline, which wins over a weaker same-run median) rather than
   failing the run.

A hard quota error from the API itself (`403`/`429` with `"quota"` in the
body) is raised immediately, not retried — retrying a quota-exhausted call
just wastes the request; only `5xx` server errors get the retry-with-backoff
treatment (3 attempts, 1.5s/3s).

## Two budgets, not one

`config.yaml` separately declares `quota.yt_daily_unit_budget` and
`quota.yt_weekly_unit_budget` (both 9000 today), and a parallel budget for
vidIQ's session-side MCP credits (`vidiq.max_credits_daily` /
`max_credits_weekly`, 5 credits per keyword-research or title-score call).
The two are independent: YouTube units are spent by this repo's own HTTP
client and tracked in-process per run; vidIQ credits are spent by whatever
session calls the MCP tool and are budgeted separately so a heavy vidIQ
day doesn't have any bearing on whether the YouTube pull can still run.
