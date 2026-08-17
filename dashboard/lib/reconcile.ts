// Shared reconcile core: pull report .md files (and their ledger rows) that live
// only on claude/* run branches onto main. Each PUT to main creates a commit,
// which auto-triggers a Vercel rebuild.
//
// This is the logic that was inline in app/api/refresh/route.ts POST. It is now
// shared so BOTH callers run the exact same code path:
//   - the user-authenticated Refresh button (app/api/refresh, POST, session-gated)
//   - the cron-authenticated scheduled reconcile (app/api/reconcile, GET, CRON_SECRET)
//
// Idempotent by construction: it builds the set of files already on main FIRST and
// skips them, so nothing stranded -> clean no-op (upToDate:true, no PUT, no rebuild).
// Safe to run repeatedly and concurrently: the report PUT omits `sha` (create path),
// so a racing writer just gets a 422 (counted in `failed`), and the next run sees the
// file on main and skips it. The ledger backfill is additive, self-healing (driven by
// report dates present on main that lack ledger rows, not just this-run recoveries),
// and never truncates: it refuses to write history.csv unless it could fully read the
// current copy (the GitHub Contents API omits the body for files >1MB, so large files
// are read via the Blobs API).

import { VERTICAL_LIST, type VerticalSlug } from './verticals';

const REPO = process.env.GITHUB_REPO || 'svx2027/yt-competitor-swipe';

type ReconcileSource = {
  vertical: VerticalSlug;
  reportsPath: string; // repo-relative path, e.g. 'reports' or 'verticals/outdoors/reports'
  historyPath: string; // repo-relative path, e.g. 'data/history.csv' or 'verticals/outdoors/data/history.csv'
};

// fitness keeps its original, unchanged repo paths (this reconcile logic predates the
// multi-vertical migration). Every other live vertical resolves to verticals/<slug>/...,
// matching what src/common.py and dashboard/scripts/ingest.mjs already resolve to for
// that vertical. Pending verticals are skipped entirely: they have no pipeline output to
// reconcile yet, and scanning for one would just be wasted GitHub API calls.
function liveSources(): ReconcileSource[] {
  return VERTICAL_LIST.filter((v) => v.status === 'live').map((v) =>
    v.slug === 'fitness'
      ? { vertical: v.slug, reportsPath: 'reports', historyPath: 'data/history.csv' }
      : {
          vertical: v.slug,
          reportsPath: `verticals/${v.slug}/reports`,
          historyPath: `verticals/${v.slug}/data/history.csv`,
        },
  );
}

export async function gh(path: string, token: string, init?: RequestInit) {
  return fetch(`https://api.github.com${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'daily-content-swipe-dashboard',
      ...(init?.headers || {}),
    },
  });
}

// Read a repo text file's utf8 content + blob sha, tolerant of GitHub's 1MB inline
// limit. The Contents API omits `content` (encoding:"none") for files 1-100MB, so we
// fall back to the Blobs API (base64 up to 100MB). Returns ok:false when the file
// genuinely could not be read, so a caller NEVER mistakes an unreadable file for an
// empty one and overwrites it. A 404 is ok:true + missing:true (file absent).
type ReadResult = { ok: boolean; content: string; sha: string | null; missing?: boolean };
async function readTextFile(ref: string, path: string, token: string): Promise<ReadResult> {
  const r = await gh(`/repos/${REPO}/contents/${path}?ref=${encodeURIComponent(ref)}`, token);
  if (r.status === 404) return { ok: true, content: '', sha: null, missing: true };
  if (!r.ok) return { ok: false, content: '', sha: null };
  const j = (await r.json()) as { content?: string; encoding?: string; sha?: string; size?: number };
  const size = j.size ?? 0;
  if (j.encoding === 'base64' && typeof j.content === 'string' && (j.content.length > 0 || size === 0)) {
    return { ok: true, content: Buffer.from(j.content, 'base64').toString('utf8'), sha: j.sha ?? null };
  }
  // Body omitted (file >1MB): fetch the blob by sha.
  if (j.sha) {
    const b = await gh(`/repos/${REPO}/git/blobs/${j.sha}`, token);
    if (b.ok) {
      const bj = (await b.json()) as { content?: string; encoding?: string };
      if (bj.encoding === 'base64' && typeof bj.content === 'string') {
        return { ok: true, content: Buffer.from(bj.content, 'base64').toString('utf8'), sha: j.sha };
      }
    }
    return { ok: false, content: '', sha: j.sha };
  }
  return { ok: false, content: '', sha: null };
}

export type ReconcileResult = {
  recovered: string[]; // report filenames copied onto main this run
  failed: string[]; // stranded reports we could not copy (fetch/PUT failed)
  strandedSeen: number; // total reports found on branches but not on main
  upToDate: boolean; // nothing stranded and every branch scanned cleanly
  rebuilding: boolean; // >=1 commit made to main -> Vercel rebuild triggered
  degraded?: boolean; // >=1 branch could not be scanned (403/5xx) -> result is not authoritative
  ledgerBackfilled?: string[]; // dates whose ledger rows were added to main this run
  ledgerFailed?: string[]; // dates whose ledger rows could not be backfilled (surfaced, not silent)
  error?: string; // set only when we bailed before scanning (e.g. GitHub down)
  status?: number; // HTTP status the caller should return when `error` is set
};

// Reconcile stranded reports onto main. Enforces an internal ~45s budget so a
// serverless invocation returns before its platform timeout; a large backlog is
// drained across successive runs (each run is idempotent). Never throws: any
// unexpected error (network failure, non-JSON body) is caught and returned as a
// graceful {error} result, matching what the Refresh-button UI and the cron expect.
export async function reconcile(token: string): Promise<ReconcileResult> {
  try {
    return await reconcileInner(token);
  } catch (e) {
    return {
      recovered: [],
      failed: [],
      strandedSeen: 0,
      upToDate: false,
      rebuilding: false,
      error: String((e as Error)?.message || e),
      status: 500,
    };
  }
}

// Reconciles every LIVE vertical against one shared ~45s budget (not 45s each), so
// adding verticals cannot blow the serverless platform's own timeout. Sources run
// sequentially (not in parallel): the ledger CAS-retry logic below assumes no other
// writer is racing it within the same invocation, which parallel sources would violate.
async function reconcileInner(token: string): Promise<ReconcileResult> {
  const deadline = Date.now() + 45_000;
  const sources = liveSources();

  const recovered: string[] = [];
  const failed: string[] = [];
  const ledgerBackfilled: string[] = [];
  const ledgerFailed: string[] = [];
  let upToDate = true;
  let rebuilding = false;
  let degraded = false;

  for (const source of sources) {
    if (Date.now() > deadline) {
      // Budget exhausted before this vertical was even scanned: its status is unknown,
      // which is exactly what `degraded` means to a caller (result not authoritative).
      degraded = true;
      break;
    }
    const r = await reconcileOneSource(token, deadline, source);
    if (r.error) {
      // A hard failure scanning this one vertical (e.g. a transient GitHub 5xx)
      // degrades the whole run rather than silently dropping that vertical's status
      // or failing every other, already-healthy vertical along with it.
      degraded = true;
      continue;
    }
    const prefix = source.vertical === 'fitness' ? '' : `${source.vertical}/`;
    recovered.push(...r.recovered.map((n) => prefix + n));
    failed.push(...r.failed.map((n) => prefix + n));
    upToDate = upToDate && r.upToDate;
    rebuilding = rebuilding || r.rebuilding;
    if (r.degraded) degraded = true;
    if (r.ledgerBackfilled) ledgerBackfilled.push(...r.ledgerBackfilled.map((d) => prefix + d));
    if (r.ledgerFailed) ledgerFailed.push(...r.ledgerFailed.map((d) => prefix + d));
  }

  return {
    recovered,
    failed,
    strandedSeen: recovered.length + failed.length,
    upToDate,
    rebuilding,
    ...(degraded ? { degraded: true } : {}),
    ...(ledgerBackfilled.length ? { ledgerBackfilled: [...new Set(ledgerBackfilled)] } : {}),
    ...(ledgerFailed.length ? { ledgerFailed: [...new Set(ledgerFailed)] } : {}),
  };
}

// Reconcile ONE vertical's stranded reports + ledger onto main. This is the original
// single-source (CAT-only) reconcile logic, unchanged except every literal 'reports' /
// 'data/history.csv' path is now source.reportsPath / source.historyPath, and the 45s
// budget is a shared `deadline` passed in rather than owned by this function.
async function reconcileOneSource(token: string, deadline: number, source: ReconcileSource): Promise<ReconcileResult> {
  const { reportsPath, historyPath } = source;
  const recovered: string[] = [];
  const failed: string[] = [];
  const ledgerBackfilled: string[] = [];
  const ledgerFailed: string[] = [];
  let degraded = false; // a branch we could not scan -> the run is not authoritative

  // 1. names already on main. A 404 here means this vertical has no reports/ path on
  // main YET, which is the normal state right up until its first report ever merges,
  // not an error: fall through with onMain empty and keep scanning branches, since
  // rescuing that very first stranded report is exactly the case reconcile exists for.
  const mainRes = await gh(`/repos/${REPO}/contents/${reportsPath}?ref=main`, token);
  let onMain = new Set<string>();
  if (mainRes.status === 404) {
    // fall through, onMain stays empty
  } else if (!mainRes.ok) {
    return {
      recovered,
      failed,
      strandedSeen: 0,
      upToDate: false,
      rebuilding: false,
      error: `github ${mainRes.status}`,
      status: 502,
    };
  } else {
    const mainItems = (await mainRes.json()) as Array<{ name: string }>;
    onMain = new Set(mainItems.filter((i) => i.name.endsWith('.md')).map((i) => i.name));
  }

  // 2. run branches (paginate up to 300). A failed page truncates discovery, so
  // mark the run degraded rather than silently reporting a clean scan.
  const branches: string[] = [];
  let morePages = false;
  for (let page = 1; page <= 3; page++) {
    const r = await gh(`/repos/${REPO}/branches?per_page=100&page=${page}`, token);
    if (!r.ok) {
      degraded = true;
      break;
    }
    const arr = (await r.json()) as Array<{ name: string }>;
    for (const b of arr) if (b.name.startsWith('claude/')) branches.push(b.name);
    if (arr.length < 100) {
      morePages = false;
      break;
    }
    morePages = true; // a full page -> there may be another beyond our cap
  }
  // Exited at the 300-branch cap with a still-full last page: discovery may be
  // truncated, so the run is not authoritative (mirrors the per-branch degraded rule).
  if (morePages) degraded = true;

  // 3. find this vertical's report files on branches but not on main (scan all
  // branches in parallel). A 404 = the branch has no <reportsPath> dir (fine, most
  // branches belong to other verticals). Any other non-ok / thrown error means we
  // could NOT scan that branch, so its reports may be invisible -> degraded.
  const stranded = new Map<string, string>(); // filename -> branch
  const listings = await Promise.all(
    branches.map(async (b) => {
      try {
        const r = await gh(`/repos/${REPO}/contents/${reportsPath}?ref=${encodeURIComponent(b)}`, token);
        if (r.status === 404) return { b, items: [] as Array<{ name: string }> };
        if (!r.ok) {
          degraded = true;
          return { b, items: [] as Array<{ name: string }> };
        }
        return { b, items: (await r.json()) as Array<{ name: string }> };
      } catch {
        degraded = true;
        return { b, items: [] as Array<{ name: string }> };
      }
    }),
  );
  for (const { b, items } of listings) {
    if (!Array.isArray(items)) continue;
    for (const it of items) {
      if (it.name.endsWith('.md') && !onMain.has(it.name) && !stranded.has(it.name)) {
        stranded.set(it.name, b);
      }
    }
  }

  // 4. copy each stranded report onto main (creates a commit -> rebuild).
  // Fetch contents in parallel; PUT sequentially so commits don't race the main ref.
  const contents = await Promise.all(
    [...stranded].map(async ([name, branch]) => {
      try {
        const cr = await gh(`/repos/${REPO}/contents/${reportsPath}/${name}?ref=${encodeURIComponent(branch)}`, token);
        if (!cr.ok) return { name, branch, content: null as string | null };
        const file = (await cr.json()) as { content?: string };
        return { name, branch, content: file.content || null };
      } catch {
        return { name, branch, content: null as string | null };
      }
    }),
  );

  for (const file of contents) {
    const { name, branch } = file;
    if (Date.now() > deadline) break;
    if (!file.content) {
      failed.push(name);
      continue;
    }
    const put = await gh(`/repos/${REPO}/contents/${reportsPath}/${name}`, token, {
      method: 'PUT',
      body: JSON.stringify({
        message: `Recover ${name} from ${branch} via dashboard refresh`,
        content: file.content.replace(/\n/g, ''),
        branch: 'main',
      }),
    });
    if (put.ok) recovered.push(name);
    else failed.push(name);
  }

  // 5. Ledger backfill: ensure every report date present on main has >=1 row in this
  // source's history.csv. Purely additive and SELF-HEALING — it is driven by on-main
  // report dates (not just this-run recoveries), so a backfill that failed or was
  // killed on a prior run is retried on the next run even though the report is already
  // on main. It NEVER truncates: it refuses to write unless it fully read the current
  // ledger (via readTextFile, which handles the >1MB Contents-API omission through the
  // Blobs API), and it re-reads + retries once on an sha race. Best-effort: never
  // throws. A ledger that does not exist on main yet (`missing`) is intentionally left
  // alone: the pipeline itself creates it on a normal publish, reconcile only backfills
  // rows into an existing file, it does not bootstrap one from nothing.
  if (Date.now() < deadline) {
    try {
      const onMainNow = new Set<string>([...onMain, ...recovered]);
      const reportDates = [
        ...new Set([...onMainNow].map((n) => n.slice(0, 10)).filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d))),
      ];
      const main = await readTextFile('main', historyPath, token);
      if (!main.ok) {
        // Could not safely read the ledger -> do NOT write (would truncate). Surface it.
        ledgerFailed.push('history.csv:unreadable');
      } else if (!main.missing && main.sha) {
        const mainDates = new Set(main.content.split('\n').map((l) => l.slice(0, 10)).filter(Boolean));
        const need = reportDates.filter((d) => !mainDates.has(d));
        if (need.length && Date.now() < deadline) {
          // Index needed date -> branches that carry a report for it. A branch holding
          // date D's report almost certainly holds D's ledger rows, so fetch ONLY those
          // branches' history.csv (bounded — never all ~300), in parallel.
          const dateBranches = new Map<string, string[]>();
          for (const { b, items } of listings) {
            if (!Array.isArray(items)) continue;
            for (const it of items) {
              const nm = (it as { name?: string })?.name;
              if (typeof nm === 'string' && nm.endsWith('.md') && need.includes(nm.slice(0, 10))) {
                const arr = dateBranches.get(nm.slice(0, 10)) || [];
                if (!arr.includes(b)) arr.push(b);
                dateBranches.set(nm.slice(0, 10), arr);
              }
            }
          }
          const relevant = [...new Set([...dateBranches.values()].flat())];
          const branchCsv = new Map<string, string>();
          await Promise.all(
            relevant.map((b) =>
              readTextFile(b, historyPath, token)
                .then((f) => branchCsv.set(b, f.ok ? f.content : ''))
                .catch(() => branchCsv.set(b, '')),
            ),
          );
          // Take each needed date's rows from the FIRST branch that has them (single
          // source -> no cross-branch (date,id) variant duplication). Only dates we
          // actually found rows for are "healed"; the rest are unsourced gaps.
          const healed: string[] = [];
          const rows: string[] = [];
          for (const d of need) {
            for (const b of dateBranches.get(d) || []) {
              const hit = (branchCsv.get(b) || '').split('\n').filter((l) => l.startsWith(d + ','));
              if (hit.length) {
                rows.push(...hit);
                healed.push(d);
                break;
              }
            }
          }
          for (const d of need) if (!healed.includes(d)) ledgerFailed.push(`${d}:no-source`);
          if (healed.length) {
            // Compare-and-swap write: merge only rows still missing, retry once on a
            // stale-sha race (409/422). Additive: existing rows are never removed.
            for (let attempt = 0; attempt < 2; attempt++) {
              const cur = attempt === 0 ? main : await readTextFile('main', historyPath, token);
              if (!cur.ok || !cur.sha) {
                ledgerFailed.push(...healed);
                break;
              }
              const curLines = new Set(cur.content.split('\n'));
              const toAdd = [...new Set(rows)].filter((l) => !curLines.has(l));
              if (!toAdd.length) {
                ledgerBackfilled.push(...healed);
                break;
              }
              const base = cur.content.replace(/\n+$/, '');
              const merged = (base ? base + '\n' : '') + toAdd.join('\n') + '\n';
              const put = await gh(`/repos/${REPO}/contents/${historyPath}`, token, {
                method: 'PUT',
                body: JSON.stringify({
                  message: `Backfill ledger rows for ${healed.join(', ')} via dashboard refresh`,
                  content: Buffer.from(merged, 'utf8').toString('base64'),
                  sha: cur.sha,
                  branch: 'main',
                }),
              });
              if (put.ok) {
                ledgerBackfilled.push(...healed);
                break;
              }
              if (attempt === 1) ledgerFailed.push(...healed);
              // else: loop, re-read a fresh sha and retry the additive merge
            }
          }
        }
      }
    } catch {
      // ledger backfill is best-effort; the report is already recovered
    }
  }

  return {
    recovered,
    failed,
    strandedSeen: stranded.size,
    // Up to date only when nothing was stranded AND every branch scanned cleanly.
    // (If the PUT loop broke on the deadline, unprocessed stranded reports are in
    // neither recovered nor failed, so gate on stranded.size, not recovered.length.)
    upToDate: stranded.size === 0 && failed.length === 0 && !degraded,
    rebuilding: recovered.length > 0,
    ...(degraded ? { degraded: true } : {}),
    ...(ledgerBackfilled.length ? { ledgerBackfilled: [...new Set(ledgerBackfilled)] } : {}),
    ...(ledgerFailed.length ? { ledgerFailed: [...new Set(ledgerFailed)] } : {}),
  };
}
