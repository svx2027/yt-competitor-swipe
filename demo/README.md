# Demo: synthetic sample report

This folder proves out the report generator (`src/report.py`,
`src/taxonomy.py`) and the scoring engine (`src/score.py`,
`src/keyword_demand.py`) without any credentials, live YouTube data, or
vidIQ/Gemini calls.

`build_sample_report.py` builds a small, entirely invented set of video and
community-post candidates for the demo vertical shipped at the repo root
(`config.yaml`, `competitors.csv`, `calendar.yaml`, `keywords.txt`,
`config/taxonomy.yml` - a fictional home-fitness-gear-review niche, not a
real channel or client), scores them with the real scoring engine, and
renders the same daily report a live run would produce.

Run it yourself:

```
pip install -r requirements.txt
python3 -m demo.build_sample_report
```

This writes `reports/<today>_daily.md` and appends `data/history.csv` -
exactly the files a real scheduled run would produce (`src/report.write_outputs`).
The copies committed in this repo are this script's own output, so you can
read a real example without running anything.

What the sample dataset exercises, so a reader can see it happen rather than
take it on faith:

- **BREAKOUT** - one channel's short massively outpaces its own recent
  uploads (20x, capped from a higher raw ratio).
- **CONVERGENCE** - three competitors post near-identical clickbait titles
  on the same hook within 48 hours.
- **CALENDAR** - a title matches the currently-active seasonal phase's boost
  hooks in `calendar.yaml`.
- **HOT_ENGAGEMENT** - comment velocity several standard deviations above
  the field.
- The keyword/demand-gap section (`src/keyword_demand.py`), computed from
  `keywords.txt` supply/demand matching with no vidIQ data present.
- Topic tagging (`src/taxonomy.py`) against `config/taxonomy.yml`, visible
  in the `topic` column of `data/history.csv`.

Point this at a real channel by replacing the five root-level files (or by
setting `VERTICAL=<name>` and creating `verticals/<name>/` with the same
five files - see `src/common.py`'s `vertical()` resolver) and running the
real pull scripts once they land (see the repo README roadmap).
