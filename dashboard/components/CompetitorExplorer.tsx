'use client';

import { useEffect, useMemo, useState } from 'react';
import Thumb from './Thumb';
import type { RadarRow } from '@/lib/competitors';

type Row = RadarRow & { year?: number };

const FORMATS: { key: '' | 'long' | 'short' | 'live'; label: string }[] = [
  { key: '', label: 'All formats' },
  { key: 'long', label: 'Long form' },
  { key: 'short', label: 'Shorts' },
  { key: 'live', label: 'Live' },
];
const SUBJECTS = ['Quants', 'LRDI', 'VARC', 'General'] as const;
// calendar-month keys (MM) so the filter matches across cycle years in combined mode
const MONTHS: { key: string; label: string }[] = [
  { key: '08', label: 'Aug' },
  { key: '09', label: 'Sep' },
  { key: '10', label: 'Oct' },
  { key: '11', label: 'Nov' },
  { key: '12', label: 'Dec' },
];
const TIERS: { key: '' | '3' | '5'; label: string }[] = [
  { key: '', label: 'All' },
  { key: '3', label: '3x+' },
  { key: '5', label: '5x+ breakouts' },
];
const FMT_LABEL: Record<string, string> = { long: 'Long', short: 'Short', live: 'Live' };

export type Filters = { fmt: string; subj: string; mon: string; tier: string; q: string };
const EMPTY: Filters = { fmt: '', subj: '', mon: '', tier: '', q: '' };
const nf = (n: number) => n.toLocaleString('en-IN');

function readFromUrl(): Filters {
  if (typeof window === 'undefined') return EMPTY;
  const p = new URLSearchParams(window.location.search);
  return {
    fmt: p.get('fmt') || '',
    subj: p.get('subj') || '',
    mon: p.get('mon') || '',
    tier: p.get('tier') || '',
    q: p.get('q') || '',
  };
}

// `initial` comes from the server, seeded off searchParams, so a shared/deep-linked
// URL renders already-filtered (no flash of the full list before hydration).
export default function CompetitorExplorer({
  rows: allRows,
  combined = false,
  initial,
}: {
  rows: Row[];
  combined?: boolean;
  initial?: Filters;
}) {
  const [f, setF] = useState<Filters>(initial ?? EMPTY);

  // keep in sync with browser back/forward (the initial state already matches the URL)
  useEffect(() => {
    const onPop = () => setF(readFromUrl());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // reflect filters into the URL (bookmark / copy-paste / back-forward) without navigation
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const p = new URLSearchParams(window.location.search);
    // preserve server-driven params (competitor c, window w); manage only the fast filters
    (['fmt', 'subj', 'mon', 'tier', 'q'] as const).forEach((k) => {
      if (f[k]) p.set(k, f[k]);
      else p.delete(k);
    });
    const qs = p.toString();
    const next = window.location.pathname + (qs ? `?${qs}` : '');
    if (next !== window.location.pathname + window.location.search) {
      window.history.replaceState(null, '', next);
    }
  }, [f]);

  const set = (patch: Partial<Filters>) => setF((prev) => ({ ...prev, ...patch }));
  const toggle = (k: keyof Filters, v: string) => set({ [k]: f[k] === v ? '' : v } as Partial<Filters>);

  const rows = useMemo(() => {
    const tier = f.tier ? Number(f.tier) : 0;
    const q = f.q.trim().toLowerCase();
    return allRows.filter(
      (r) =>
        (!f.fmt || r.fmt === f.fmt) &&
        (!f.subj || r.subject === f.subj) &&
        (!f.mon || r.month.slice(5) === f.mon) && // match on calendar month across years
        (!tier || (r.mult ?? 0) >= tier) &&
        (!q || r.title.toLowerCase().includes(q)),
    );
  }, [allRows, f]);

  const kpis = useMemo(() => {
    const known = rows.filter((r) => r.views != null).map((r) => r.views as number);
    const sorted = [...known].sort((a, b) => a - b);
    const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
    const total = known.reduce((s, v) => s + v, 0);
    const breakouts = rows.filter((r) => (r.mult ?? 0) >= 5).length;
    return { count: rows.length, median, total, breakouts };
  }, [rows]);

  const active = f.fmt || f.subj || f.mon || f.tier || f.q;

  return (
    <div className="radar">
      <div className="radar-kpis">
        <Kpi n={nf(kpis.count)} k="Videos" />
        <Kpi n={kpis.median ? nf(kpis.median) : 'n/a'} k="Median views" />
        <Kpi n={nf(kpis.total)} k="Total views" />
        <Kpi n={nf(kpis.breakouts)} k="5x+ breakouts" accent />
      </div>

      <div className="radar-filters">
        <div className="seg" role="group" aria-label="Format">
          {FORMATS.map((o) => (
            <button
              key={o.key || 'all'}
              type="button"
              className={`seg-btn${f.fmt === o.key ? ' on' : ''}`}
              aria-pressed={f.fmt === o.key}
              onClick={() => set({ fmt: o.key })}
            >
              {o.label}
            </button>
          ))}
        </div>

        <div className="radar-chiprow" role="group" aria-label="Subject">
          {SUBJECTS.map((s) => (
            <button
              key={s}
              type="button"
              className={`radar-chip${f.subj === s ? ' on' : ''}`}
              aria-pressed={f.subj === s}
              onClick={() => toggle('subj', s)}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="radar-chiprow" role="group" aria-label="Month">
          {MONTHS.map((m) => (
            <button
              key={m.key}
              type="button"
              className={`radar-chip${f.mon === m.key ? ' on' : ''}`}
              aria-pressed={f.mon === m.key}
              onClick={() => toggle('mon', m.key)}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div className="seg" role="group" aria-label="Outlier tier">
          {TIERS.map((t) => (
            <button
              key={t.key || 'all'}
              type="button"
              className={`seg-btn${f.tier === t.key ? ' on' : ''}`}
              aria-pressed={f.tier === t.key}
              onClick={() => set({ tier: t.key })}
            >
              {t.label}
            </button>
          ))}
        </div>

        <input
          className="radar-search"
          type="search"
          placeholder="Search title…"
          value={f.q}
          onChange={(e) => set({ q: e.target.value })}
          aria-label="Search title"
        />
        {active ? (
          <button type="button" className="btn text" onClick={() => setF(EMPTY)}>
            Reset
          </button>
        ) : null}
      </div>

      {rows.length === 0 ? (
        <div className="radar-empty">
          <p>Nothing matched those filters.</p>
          <button type="button" className="btn" onClick={() => setF(EMPTY)}>
            Reset filters
          </button>
        </div>
      ) : (
        <div className="radar-table" role="table" aria-label="Competitor videos">
          <div className="radar-head" role="row">
            <span role="columnheader">#</span>
            <span role="columnheader">Video</span>
            <span role="columnheader" className="num">
              Views
            </span>
            <span role="columnheader" className="num">
              x median
            </span>
            <span role="columnheader" className="num">
              Views/day
            </span>
            <span role="columnheader">2026 beat</span>
          </div>
          {rows.map((r, i) => (
            <Row key={`${r.year ?? ''}-${r.id}`} r={r} rank={i + 1} combined={combined} />
          ))}
        </div>
      )}
      <p className="radar-foot muted">
        x median = views divided by that format&apos;s median in this window (5x+ = at least five times its normal). Live
        streams dated by air time, uploads by publish time (IST). &ldquo;n/a&rdquo; means the count was unavailable, never
        zero.
      </p>
    </div>
  );
}

function Kpi({ n, k, accent }: { n: string; k: string; accent?: boolean }) {
  return (
    <div className={`radar-kpi${accent ? ' accent' : ''}`}>
      <div className="n">{n}</div>
      <div className="k">{k}</div>
    </div>
  );
}

function Row({ r, rank, combined }: { r: Row; rank: number; combined: boolean }) {
  const breakout = (r.mult ?? 0) >= 5;
  const strong = !breakout && (r.mult ?? 0) >= 3;
  return (
    <a className="radar-row" role="row" href={r.url} target="_blank" rel="noreferrer noopener">
      <span className="radar-rank" role="cell">
        {rank}
      </span>
      <span className="radar-vid" role="cell">
        <Thumb id={r.id} alt="" />
        <span className="radar-vidmeta">
          <span className="radar-title">{r.title}</span>
          <span className="radar-sub">
            {combined && r.year ? <span className={`radar-year y-${r.year}`}>{r.year}</span> : null}
            <span className={`radar-subj s-${r.subject}`}>{r.subject}</span>
            <span className="radar-dot">·</span>
            <span>{FMT_LABEL[r.fmt]}</span>
            <span className="radar-dot">·</span>
            <span>{r.date}</span>
            <span className="radar-dot">·</span>
            <span className="radar-theme">{r.theme}</span>
            {r.premiere ? <span className="radar-flag">premiere</span> : null}
          </span>
        </span>
      </span>
      <span className="radar-cell num" role="cell" data-label="Views">
        {r.views == null ? 'n/a' : nf(r.views)}
      </span>
      <span className="radar-cell num" role="cell" data-label="x median">
        {r.mult == null ? (
          'n/a'
        ) : (
          <span className={`radar-mult${breakout ? ' breakout' : strong ? ' strong' : ''}`}>{r.mult}x</span>
        )}
      </span>
      <span className="radar-cell num" role="cell" data-label="Views/day">
        {r.vpd == null ? 'n/a' : nf(Math.round(r.vpd))}
      </span>
      <span className="radar-cell" role="cell" data-label="Publish for 2026">
        {r.m26 ? <span className="radar-beat">{r.m26}</span> : '—'}
      </span>
    </a>
  );
}
