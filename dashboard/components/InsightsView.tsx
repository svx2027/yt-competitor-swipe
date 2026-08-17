'use client';

import { useEffect, useState } from 'react';
import Thumb from './Thumb';
import type { InsightsData, InsightRef, FocusItem, RadarFormat } from '@/lib/competitors';

const MONTHS = [
  { key: '08', label: 'August' },
  { key: '09', label: 'September' },
  { key: '10', label: 'October' },
  { key: '11', label: 'November' },
  { key: '12', label: 'December' },
];
const FMT_LABEL: Record<RadarFormat, string> = { long: 'Long form', short: 'Shorts', live: 'Live streams' };
const KIND_LABEL: Record<FocusItem['kind'], string> = {
  repeated: 'Worked both years',
  rising: 'New in 2025',
  faded: 'Faded from 2024',
};
const nf = (n: number | null) => (n == null ? 'n/a' : n.toLocaleString('en-IN'));

export default function InsightsView({ data, initialMonth }: { data: InsightsData; initialMonth?: string }) {
  const first = MONTHS.some((m) => m.key === initialMonth) ? (initialMonth as string) : '08';
  const [mm, setMm] = useState(first);
  const years = data.years;

  useEffect(() => {
    const onPop = () => {
      const p = new URLSearchParams(window.location.search).get('m');
      if (p && MONTHS.some((m) => m.key === p)) setMm(p);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const pick = (k: string) => {
    setMm(k);
    const p = new URLSearchParams(window.location.search);
    p.set('m', k);
    window.history.replaceState(null, '', window.location.pathname + '?' + p.toString());
  };

  const month = data.months[mm];

  return (
    <div className="ins">
      <div className="ins-monthbar" role="tablist" aria-label="Month">
        {MONTHS.map((m) => (
          <button
            key={m.key}
            role="tab"
            aria-selected={mm === m.key}
            className={`ins-monthchip${mm === m.key ? ' on' : ''}`}
            onClick={() => pick(m.key)}
          >
            {m.label}
          </button>
        ))}
      </div>

      {!month ? (
        <p className="muted">No data for this month.</p>
      ) : (
        <>
          <h2 className="ins-h">
            In {month.label}, focus on these
            <span className="ins-sub">
              {years.map((y) => `${y}: ${month.counts[String(y)] ?? 0} videos`).join('  ·  ')}
            </span>
          </h2>

          <div className="ins-focus">
            {month.focus.length === 0 && <p className="muted">No standout patterns this month.</p>}
            {month.focus.map((fi, i) => (
              <div key={i} className={`ins-card k-${fi.kind}`}>
                <div className="ins-card-top">
                  <span className={`ins-kind k-${fi.kind}`}>{KIND_LABEL[fi.kind]}</span>
                  <span className={`radar-subj s-${fi.subject}`}>{fi.subject}</span>
                  <span className="ins-fmt">{FMT_LABEL[fi.fmt]}</span>
                  {fi.target_2026 && <span className="ins-target">Publish by {beforeDate(fi.target_2026)}</span>}
                </div>
                <div className="ins-headline">{fi.headline}</div>
                <div className="ins-why muted">{fi.why}</div>
                <div className="ins-refs">
                  {fi.refs.map((r, j) => (
                    <RefChip key={j} r={r} />
                  ))}
                </div>
              </div>
            ))}
          </div>

          <h3 className="ins-h3">Top videos by format, both years</h3>
          <div className="ins-formats">
            {(['long', 'short', 'live'] as RadarFormat[]).map((fmt) => (
              <div key={fmt} className="ins-fmtblock">
                <div className="ins-fmtname">{FMT_LABEL[fmt]}</div>
                <div className="ins-fmtcols">
                  {years.map((y) => {
                    const list = (month.by_format[String(y)]?.[fmt] || []).slice(0, 5);
                    return (
                      <div key={y} className="ins-fmtcol">
                        <div className={`ins-year y-${y}`}>{y}</div>
                        {list.length === 0 && <div className="ins-none muted">none</div>}
                        {list.map((r, k) => (
                          <a key={k} className="ins-vid" href={r.url} target="_blank" rel="noreferrer noopener">
                            <Thumb id={r.id} alt="" />
                            <span className="ins-vidmeta">
                              <span className="ins-vidtitle">{r.title}</span>
                              <span className="ins-vidnums">
                                {nf(r.views)} · <b>{r.mult ?? '?'}x</b>
                              </span>
                            </span>
                          </a>
                        ))}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
      <p className="radar-foot muted">
        &ldquo;Worked both years&rdquo; means the theme cleared 3x its format median in {years.join(' and ')}, the
        strongest signal to repeat. Ranked by outlier multiple (age-fair across years). Publish-by dates map each winner
        to the active seasonal calendar, three days before the matching event.
      </p>
    </div>
  );
}

function RefChip({ r }: { r: InsightRef }) {
  return (
    <a className="ins-refchip" href={r.url} target="_blank" rel="noreferrer noopener">
      <span className={`ins-year y-${r.year}`}>{r.year}</span>
      <span className="ins-reftitle">{r.title}</span>
      <span className="ins-refnum">
        {nf(r.views)} · {r.mult ?? '?'}x
      </span>
    </a>
  );
}

function beforeDate(iso: string): string {
  // show the target date minus 3 days, dd Mon
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() - 3);
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' });
}
