# YT Competitor Swipe dashboard

Reports dashboard for the yt-competitor-swipe pipeline. Lives inside the
pipeline repo so every routine push (report + ledger) automatically redeploys
the site with the new report baked in.

## How it works

- `scripts/ingest.mjs` runs before every build (`prebuild`). It auto-discovers
  every configured vertical (fitness's original root-level `../reports` and
  `../data/history.csv`, plus any `verticals/<name>/reports` subdirectory),
  parses each vertical's `*.md` reports into structured JSON under
  `.content/<vertical>/`, and runs the **verification gate**: filename/date/kind
  recognition, PAGE 1 pick count vs the preface funnel line, YouTube video-id
  extraction, and cross-checks against that vertical's `history.csv` (rows
  exist for the report date, pick ids exist in the ledger). Reports that fail
  hard checks are **held** (not published, listed on the home banner); soft
  mismatches publish with a `warned` badge and the reasons shown.
- `lib/verticals.ts` is the single registry of every niche the dashboard
  serves (slug, display name, accent colors, calendar path, live/pending
  status). Adding a niche is a one-file change there plus that niche's content;
  every other module (auth, middleware, content, share, routing) reads from
  this registry instead of hardcoding vertical slugs.
- Pages are statically generated per report (`/<vertical>/r/<slug>`); the
  calendar only activates days that have a verified/warned report. Daily = dot,
  weekly = ✱, monthly retro = M (placed on its `Generated` date).
- Thumbnails come from `https://i.ytimg.com/vi/<id>/hqdefault.jpg` — no storage.

## Auth

Two independent sign-in paths, both gated by `middleware.ts` on every route
except `/login`, `/api/auth/*`, and `/share/*`:

- **Google sign-in (Auth.js v5)** with a hard allowlist — only emails in
  `ALLOWED_EMAILS` get a session, and are treated as admin (able to view every
  vertical, with a vertical switcher in the header).
- **Per-vertical credential login** — `CLIENT_<VERTICAL>_USERNAME` /
  `CLIENT_<VERTICAL>_PASSWORD_HASH` env vars (PBKDF2 hash, see
  `scripts/hash-password.mjs`), scoped to that one vertical only.

JWT session cookie (HTTP-only, secure), 30-day max age. `noindex` headers +
`robots.txt` disallow while iterating; treat the deployed URL as unlisted, not
public-indexed.

## Share links

- `POST /api/share {slug, days}` (session required) returns
  `/share/<signed JWT>` — read-only view of one report, expiring after
  `days` (1–365, chosen in the Share panel).
- **Revoke all outstanding links**: rotate `SHARE_SECRET` in Vercel env and
  redeploy. Individual links cannot be revoked (stateless tokens) — rotation
  is a blunt but total kill switch.

## Environment variables (Vercel → Settings → Environment Variables)

See `.env.example`. `AUTH_SECRET`, `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`,
`ALLOWED_EMAILS`, `SHARE_SECRET`. Local dev uses `.env.local` (gitignored).

## Vercel project settings

- Root Directory: `dashboard` (with "Include source files outside of the Root
  Directory" enabled — the ingest script reads `../reports`, `../data`, and
  `../verticals/*`).
- Domain: set your own custom domain, or use the default `*.vercel.app` URL —
  deployed on Vercel either way.

## Format contract

The pipeline's own report-generation code (`src/report.py` and friends) and
this dashboard's parser (`scripts/ingest.mjs`) share a structural contract:
field labels like `Strategist take:` and the PAGE 1 pick-count line must match
exactly. Change the report format and the ingest parser together, and keep the
gate green.

## Status

This ships running on the repo's demo `fitness` (home fitness gear review)
data — the same niche `calendar.yaml`, `reports/`, and `data/history.csv`
already power in the Python engine one level up. A second niche, `outdoors`,
is wired in `lib/verticals.ts` with `status: 'pending'` and no content yet, to
demonstrate the multi-niche architecture: it renders a "coming soon" page
today and needs no code changes to go live once its own reports exist.
