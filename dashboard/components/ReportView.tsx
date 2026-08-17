'use client';

import { useState } from 'react';
import Thumb from './Thumb';
import CopyButton from './CopyButton';
import { VERTICALS, type VerticalSlug } from '@/lib/verticals';

const KIND_LABEL: Record<string, string> = { daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly retro' };

function Stats({ text }: { text: string }) {
  if (!text) return null;
  return (
    <span className="stats">
      {text.split('|').map((s, i) => (
        <span className="chip stat" key={i}>
          {s.trim()}
        </span>
      ))}
    </span>
  );
}

function PickCard({ p, takeLabel }: { p: any; takeLabel: string }) {
  return (
    <article className="pick">
      <a className="pick-thumb" href={p.link || undefined} target="_blank" rel="noreferrer">
        <Thumb id={p.videoId} alt={p.title} />
        <span className="fmt">{p.format}</span>
      </a>
      <div className="pick-body">
        <div className="pick-rank">
          #{p.rank} <span className="hook">{p.hook}</span>
        </div>
        <a href={p.link || undefined} target="_blank" rel="noreferrer" className="title-link">
          <h3>{p.title}</h3>
        </a>
        <p className="muted">{p.channel}</p>
        <Stats text={p.stats} />
        {p.take && (
          <p className="take">
            <strong>{takeLabel}</strong> {p.take}
          </p>
        )}
      </div>
    </article>
  );
}

function WinnerCard({ w, takeLabel }: { w: any; takeLabel: string }) {
  return (
    <article className="pick slim">
      {w.videoId && (
        <a className="pick-thumb" href={w.link || undefined} target="_blank" rel="noreferrer">
          <Thumb id={w.videoId} alt={w.title} />
          <span className="fmt">{w.format}</span>
        </a>
      )}
      <div className="pick-body">
        <div className="pick-rank">
          #{w.rank} <span className="chip stat">{w.format}</span>
        </div>
        <h3>{w.title}</h3>
        <p className="muted">{w.channel}</p>
        {w.take && (
          <p className="take">
            <strong>{takeLabel}</strong> {w.take}
          </p>
        )}
      </div>
    </article>
  );
}

function EntryRow({ e, takeLabel }: { e: any; takeLabel: string }) {
  const f = e.fields || {};
  // NOTE: `f['Strategist take']` is a raw pass-through data key parsed straight from the
  // pipeline's report markdown (see dashboard/scripts/ingest.mjs), not a display
  // string. It stays a literal lookup regardless of vertical; only the label shown
  // to the user (the <strong> text below) becomes vertical-aware.
  return (
    <article className="entry">
      <a className="entry-thumb" href={f.Link || undefined} target="_blank" rel="noreferrer">
        <Thumb id={e.videoId} alt={e.title} />
      </a>
      <div className="entry-body">
        <a href={f.Link || undefined} target="_blank" rel="noreferrer" className="title-link">
          <h4>
            [{e.rank}] {e.title}
          </h4>
        </a>
        <p className="muted small">
          {[f.Channel, f.Posted].filter(Boolean).join(', ')}
        </p>
        {(f.Engagement || f.Flags) && (
          <p className="muted small">{[f.Engagement, f.Flags].filter(Boolean).join(' | ')}</p>
        )}
        {f.Why && (
          <p className="small why">
            <strong>Why</strong> {f.Why}
          </p>
        )}
        {f['Audience read'] && (
          <p className="small why">
            <strong>Audience read</strong> {f['Audience read']}
          </p>
        )}
        {f['Strategist take'] && (
          <p className="take small">
            <strong>{takeLabel}</strong> {f['Strategist take']}
          </p>
        )}
      </div>
    </article>
  );
}

function Lines({ lines }: { lines: string[] }) {
  if (!lines?.length) return null;
  return <pre className="block">{lines.join('\n')}</pre>;
}

export default function ReportView({
  report,
  shared = false,
  takeLabel = 'Strategist take',
  vertical,
}: {
  report: any;
  shared?: boolean;
  takeLabel?: string;
  vertical?: VerticalSlug;
}) {
  const tabs =
    report.kind === 'daily'
      ? ['Top picks', 'Full report', 'Raw']
      : report.kind === 'weekly'
        ? ['Overview', 'Full report', 'Raw']
        : ['Retro', 'Raw'];
  const [tab, setTab] = useState(tabs[0]);
  const v = report.verification || { status: 'verified', checks: [] };
  const failed = v.checks.filter((c: any) => !c.ok);
  const productName = vertical ? `${VERTICALS[vertical].name} Intelligence` : 'Client Intelligence';

  return (
    <div className="report">
      <div className="rep-head">
        <div className="chips">
          <span className={`chip kind ${report.kind}`}>{KIND_LABEL[report.kind]}</span>
          <span className={`chip st ${v.status}`} title={failed.map((c: any) => `${c.label}: ${c.note}`).join('\n') || 'All checks passed'}>
            {v.status === 'verified' ? '✓ verified' : v.status}
          </span>
        </div>
        <h1>{report.headerTitle}</h1>
        <p className="muted small">{[report.generated, report.sources].filter(Boolean).join(' · ')}</p>
        {failed.length > 0 && (
          <div className="banner warn small">
            {failed.map((c: any, i: number) => (
              <div key={i}>
                {c.label}: {c.note}
              </div>
            ))}
          </div>
        )}
      </div>

      {report.preface?.length > 0 && (
        <details className="preface">
          <summary>What this run did</summary>
          <Lines lines={report.preface} />
        </details>
      )}

      <div className="tabs">
        {tabs.map((t) => (
          <button key={t} className={`tab${t === tab ? ' on' : ''}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === 'Top picks' && (
        <div className="picks">
          {report.picks.map((p: any) => (
            <PickCard key={p.rank} p={p} takeLabel={takeLabel} />
          ))}
          {report.extras?.map((x: any, i: number) => (
            <div className="extra" key={i}>
              <h4>{x.label}</h4>
              <Lines lines={x.lines} />
            </div>
          ))}
        </div>
      )}

      {tab === 'Overview' && (
        <div className="picks">
          {report.weeklyGroups?.map((g: any, i: number) => (
            <div className="wgroup" key={i}>
              <h4>{g.label}</h4>
              {g.winners.map((w: any) => (
                <WinnerCard key={w.rank} w={w} takeLabel={takeLabel} />
              ))}
              <Lines lines={g.lines} />
            </div>
          ))}
        </div>
      )}

      {tab === 'Retro' && (
        <div className="picks">
          {report.sections.map((s: any, i: number) => (
            <div className="wgroup" key={i}>
              <h4>{s.name}</h4>
              <Lines lines={s.lines} />
            </div>
          ))}
        </div>
      )}

      {tab === 'Full report' && (
        <div className="sections">
          {report.sections.map((s: any, i: number) => (
            <section key={i}>
              <h3 className="sec-name">{s.name}</h3>
              {s.entries.length > 0 ? (
                s.entries.map((e: any) => <EntryRow key={`${i}-${e.rank}`} e={e} takeLabel={takeLabel} />)
              ) : (
                <Lines lines={s.lines} />
              )}
            </section>
          ))}
        </div>
      )}

      {tab === 'Raw' && (
        <div className="copy-wrap">
          <CopyButton text={report.raw} />
          <pre className="block raw">{report.raw}</pre>
        </div>
      )}

      {shared && <p className="foot">{productName} · shared read-only copy</p>}
    </div>
  );
}
