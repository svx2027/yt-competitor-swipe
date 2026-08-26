# Scoring: how the Opportunity Score is built

The Opportunity Score is a blended 0-100 ranking computed once per candidate
(video or community post) in `src/score.py`, using weights and thresholds
that all live in `config.yaml` — nothing here is hardcoded in Python. This
doc is the worked reference for exactly how those numbers combine; the
signal descriptions in the README's "The signals" table are the summary,
this is the arithmetic.

## The six weighted components (videos)

`config.yaml`'s `weights` block sums to 100. Each component is first
normalized to its own 0-100 scale (`c_*` below), then blended:

```
raw = (weights.vph        * c_vph
     + weights.outlier    * c_outlier
     + weights.engagement * c_engagement
     + weights.demand_gap * c_demand_gap
     + weights.convergence* c_convergence
     + weights.calendar   * c_calendar) / 100
```

| Component | Default weight | How `c_*` (0-100) is computed |
|---|---|---|
| `vph` | 35 | Percentile rank of the video's views-per-hour against every other video scored in the same run (`_pct_rank`). Relative, not absolute — a slow news day doesn't zero out the top pick. |
| `outlier` | 25 | `outlier multiple / 5.0`, clamped to 0-100. The multiple itself (views vs. the channel's own expected pace) is capped differently — see "Two outlier caps" below. |
| `engagement` | 15 | `50 + 20 * engagement_velocity`, clamped to 0-100. Centers a video with average engagement at 50; see the subweights below for what feeds `engagement_velocity`. |
| `demand_gap` | 10 | Taken directly from `keyword_demand`'s 0-100 score (a rising query with thin or stale supply scores high; no video with any real demand signal scores 0). |
| `convergence` | 10 | `cluster size / (min_cluster_size + 2)`, clamped to 0-100. `cluster size` is the count of distinct competitor channels posting on the same title subtopic within the convergence window. |
| `calendar` | 5 | The fraction of the active seasonal phase's `boost_hooks` tokens that overlap the title's tokens, times 100. Zero when no calendar phase is active. |

`raw` is the score before relation weighting; `opportunity_score` (the
number actually shown and sorted on) is `raw * relation_weights[relation]`.

## Relation weighting

Applied only to the final score, never to any `c_*` component, so a
self-channel or indirect-competitor video is still fully visible everywhere
in the report — it just doesn't out-rank direct competitors in the "make
this" ordering:

| Relation | Weight | Effect |
|---|---|---|
| `direct` | 1.0 | Full score |
| `indirect` | 0.8 | Scaled down 20% |
| `self` | 0.0 | Excluded from ranking entirely (used only as an outlier baseline) |

## Engagement subweights

`engagement_velocity` (the input to the `engagement` component above) is
itself a weighted sum of three z-scores, each computed across the day's
full video distribution (`common.zscores`):

```
engagement_velocity = engagement_subweights.comment_vph_z * comment_vph_z
                     + engagement_subweights.like_vph_z    * like_vph_z
                     + engagement_subweights.eng_rate_z    * eng_rate_z
```

Defaults: comment velocity 0.50, like velocity 0.30, engagement-rate 0.20 —
comment velocity leads because a comment costs the viewer more effort than
a like, so it's read as the stronger interest signal.

## Two outlier caps, not one

`compute_outliers` (views vs. the channel's own expected pace, preferred
source order: vidIQ's own outlier score, then a rolling per-channel
baseline in `cache/baselines.json`, then the day's own same-channel median
as a last resort) caps the **displayed** multiple at 20x — lifetime-VPH
baselines understate "expected fresh VPH", so the raw ratio can otherwise
balloon into a number nobody would trust. The **scoring** component caps at
a separate, tighter `outlier_cap = 5.0` before converting to `c_outlier`,
so one extreme outlier can't single-handedly dominate the blended score
even though the report still shows its true (up to 20x) multiple.

## Flags and their thresholds (`config.yaml` → `flags`, `sleeper`, `convergence`)

Flags are independent of the Opportunity Score — a video can be flagged
without ranking highly, and vice versa:

| Flag | Fires when |
|---|---|
| `BREAKOUT` | `outlier >= flags.breakout_outlier_min` (default 2.0x) |
| `HOT_ENGAGEMENT` | `comment_vph_z >= flags.hot_engagement_z_min` (default 1.5) |
| `CONVERGENCE` | cluster's recent-channel count `>= convergence.min_cluster_size` (default 3) within `convergence.window_hours` (default 48h) |
| `CALENDAR` | title/hook token overlap `>= 0.5` against the active seasonal phase |
| `SLEEPER` | video is older than `sleeper.min_age_hours` (48h) and its VPH grew `>= sleeper.min_vph_growth_pct` (25%) since the last time it was seen in `data/history.csv` |
| `NEW_FORMAT` | channel posts a format (`short`/`long`/`live`) it hasn't used in `flags.new_format_lookback_days` (30 days) — only once that channel has `flags.new_format_min_history_rows` (8) rows of history, so a thin history doesn't make every format look new |

## Clustering (feeds `convergence`)

Title clustering tries the Gemini fast model first (`cluster_videos`), and
falls back to a deterministic local method (group each title under its
single rarest significant token, `_local_clusters`) whenever Gemini is
disabled, over the `gemini.cluster_batch` size, or the API call fails for
any reason — the convergence signal never depends on an external API being
up. Before clustering, tokens appearing in more than `cluster_max_df`
(default 40%) of titles are dropped as corpus-noise unless they're an
explicit `niche.cluster_anchor_tokens` entry — otherwise a channel's own
recurring brand word would bridge every video into one mega-cluster.

## Community posts score differently

Posts have no views-per-hour or outlier signal, so `_score_posts` uses a
separate, simpler blend (not configurable in `config.yaml` today — a fixed
formula in code):

```
raw = 0.45 * like_percentile + 0.35 * (100 if poll else 0) + 0.20 * calendar_match * 100
```

The same `relation_weights` scaling applies afterward. A poll gets a flat
bonus rather than a computed one because a poll's engagement shape (vote
counts, not likes) isn't comparable to a text or image post's.

## Changing the weights

Every number above is a `config.yaml` value, not a code constant. Retuning
a niche's priorities — e.g. weighting `outlier` higher than `vph` for a
channel where raw view counts are noisy but breakout ratio is reliable — is
a config edit, not a `src/score.py` change.
