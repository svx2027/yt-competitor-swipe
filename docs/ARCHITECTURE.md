# Architecture

How yt-competitor-swipe turns a list of competitor channels into a ranked,
sourced report and a browsable dashboard.

## Pipeline stages

```
competitors.csv + keywords.txt          (who to watch, what to search for)
        |
        v
  src/youtube_pull.py    YouTubeClient   ---> raw candidates (videos, one dict each)
        |                                     see CANDIDATE_FIELDS in src/common.py
        v
  src/score.py            scoring        ---> outlier multiple, engagement z-scores,
        |                                     clustering, calendar tailwind, flags,
        |                                     the blended 0-100 Opportunity Score
        v
  src/keyword_demand.py   demand gap     ---> rising queries with thin/stale supply
        v
  src/taxonomy.py         topic tagging  ---> rule-based subject label per pick
        v
  src/report.py           assembly       ---> reports/<date>_daily.md (or _weekly.md)
        v
  src/common.py           ledger I/O     ---> data/history.csv (append + dedupe, tracked in git)
        v
  dashboard/               (Next.js)     ---> parses reports/*.md at build time, serves
                                              per-report pages, share links, auth
```

Each stage reads and enriches the same in-memory candidate dict (schema
documented in `src/common.py`'s `CANDIDATE_FIELDS`) rather than passing
separate data structures between modules — `youtube_pull` fills in the raw
signal fields, `score` adds the ranking fields, `report` adds the narrative
fields. The repo itself is the delivery surface: `reports/` and
`data/history.csv` are committed, not emailed or pushed to a spreadsheet.

## What each module owns

- **`src/common.py`** — config/vertical path resolution (see Multi-vertical
  below), time helpers (fixed IST offset), z-score/clamp maths, the
  candidate schema, and the header-driven ledger reader/writer
  (`data/history.csv`). "Header-driven" means every CSV read/write goes
  through named columns, never positional indexing — so a hand-added column
  or an evolving schema doesn't silently corrupt rows.
- **`src/youtube_pull.py`** — the only module that talks to the YouTube Data
  API. Channel resolution, upload-playlist pulls, short/longform/livestream
  classification (`liveBroadcastContent` first, then a `/shorts/<id>`
  redirect probe for the 61–180s ambiguous band), and candidate assembly.
  Quota accounting lives here — see `docs/API_QUOTA.md`.
- **`src/score.py`** — outlier multiple against a per-channel baseline,
  z-scored engagement velocity, title clustering into subtopics (Gemini
  when available, a deterministic local token-anchor fallback otherwise —
  the signal never depends on an external API being up), calendar-phase
  tailwind, sleeper re-acceleration, and the weighted 0–100 Opportunity
  Score (weights are config, not code — see `config.yaml`).
- **`src/keyword_demand.py`** — the demand/supply gap signal. Reads vidIQ
  keyword data from `cache/vidiq_keywords.json` when a session has written
  it (vidIQ is an MCP tool, so it's fetched session-side, not by this
  module); degrades to a static keyword universe plus supply strength
  computed from the day's own pull when that cache is absent, so the
  section always renders something honest rather than going empty.
- **`src/taxonomy.py`** — rule-based topic tagging for the ledger's `topic`
  column.
- **`src/report.py`** — assembles the daily or weekly Markdown report
  (`build_daily_report` / `build_weekly_report`): preface, ranked sections,
  a demand-gap appendix, fallback narrative text when no session-authored
  "strategist take" exists yet.
- **`dashboard/`** — a separate Next.js app that reads the committed
  `reports/*.md` and `data/history.csv` at build time (`scripts/ingest.mjs`,
  run as a `prebuild` step) and serves static per-report pages, Google or
  per-vertical credential auth, and expiring share links. See
  `dashboard/README.md` for its own architecture (auth paths, the
  verification gate ingest runs before publishing a report, the multi-niche
  registry in `lib/verticals.ts`).

## Multi-vertical design

Every path a run needs — `config.yaml`, `calendar.yaml`, `keywords.txt`,
`competitors.csv`, `config/taxonomy.yml` — is resolved through
`common.py`'s `_vertical_path()`, keyed off the `VERTICAL` env var. Unset or
`main` resolves to the repo-root files (a single-niche setup is unaffected);
any other value resolves to `verticals/<name>/` with the same five files.
This lets one engine track more than one niche side by side without their
configs colliding, and it's why the dashboard's own vertical registry
(`lib/verticals.ts`) is a one-file addition per niche rather than a code
change.

## Honest scope

Two modules the docstring in `src/common.py` and `config.yaml` reference —
a community-post scraper (`community_pull`) and a Gemini thumbnail-vision
reader (`vision`) — are configured for (`community:` / `vision:` blocks in
`config.yaml`) but not yet ported to this public repo. The scoring and
report code tolerates their absence (posts are handled as an empty list;
`thumbnail_read` stays `None`), so the pipeline runs correctly without them
— they're future work, not a missing dependency.

Likewise, `config.yaml`'s `deadline.monthly_finalize_ist` and
`report.brand_header_monthly`, and the dashboard's monthly-retro calendar
marker (`dashboard/README.md`), describe a third report cadence alongside
daily and weekly — but `src/report.py` currently only implements
`build_daily_report` and `build_weekly_report`. The monthly config keys are
present for forward compatibility; the monthly report builder itself isn't
ported yet.

## Demo data

`config.yaml`, `competitors.csv`, `calendar.yaml`, `keywords.txt`,
`config/taxonomy.yml`, and everything under `demo/`, `reports/`, and
`data/history.csv` describe a fictional home-fitness-gear-review niche,
invented for this public repo — not a real deployment's configuration. See
`demo/README.md` for how the sample report was generated.
