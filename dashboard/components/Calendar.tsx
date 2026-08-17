'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import type { VerticalSlug } from '@/lib/verticals';

const KIND_LABEL: Record<string, string> = { daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly retro' };
const KIND_MARK: Record<string, string> = { daily: '•', weekly: '✱', monthly: 'M' };
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

type Entry = { slug: string; kind: string; status: string };

export default function Calendar({
  byDate,
  latestDate,
  vertical,
}: {
  byDate: Record<string, Entry[]>;
  latestDate: string | null;
  vertical: VerticalSlug;
}) {
  const router = useRouter();
  const [open, setOpen] = useState<string | null>(null);

  const MONTH_CAP = 3;
  const { months, olderCount } = useMemo(() => {
    const dates = Object.keys(byDate).sort();
    if (!dates.length) return { months: [] as string[], olderCount: 0 };
    const first = dates[0].slice(0, 7);
    const last = dates[dates.length - 1].slice(0, 7);
    const list: string[] = [];
    let y = +first.slice(0, 4);
    let m = +first.slice(5, 7);
    while (true) {
      const key = `${y}-${String(m).padStart(2, '0')}`;
      list.push(key);
      if (key === last) break;
      m++;
      if (m > 12) {
        m = 1;
        y++;
      }
    }
    const reversed = list.reverse();
    return { months: reversed.slice(0, MONTH_CAP), olderCount: Math.max(0, reversed.length - MONTH_CAP) };
  }, [byDate]);

  function dayClick(key: string, entries: Entry[]) {
    if (entries.length === 1) {
      router.push(`/${vertical}/r/${entries[0].slug}`);
    } else {
      setOpen(open === key ? null : key);
    }
  }

  return (
    <div className="cal" onMouseLeave={() => setOpen(null)}>
      <div className="cal-head-row">
        <h2>Report calendar</h2>
        <div className="cal-legend">
          <span>• daily</span>
          <span>✱ weekly</span>
          <span>M monthly retro</span>
          {olderCount > 0 && (
            <span className="muted">
              +{olderCount} earlier month{olderCount > 1 ? 's' : ''} not shown
            </span>
          )}
        </div>
      </div>
      <div className="cal-months">
        {months.map((mo) => {
          const y = +mo.slice(0, 4);
          const m = +mo.slice(5, 7);
          const firstDow = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7;
          const daysIn = new Date(Date.UTC(y, m, 0)).getUTCDate();
          const cells: (number | null)[] = [
            ...Array.from({ length: firstDow }, () => null),
            ...Array.from({ length: daysIn }, (_, i) => i + 1),
          ];
          return (
            <div className="cal-month" key={mo}>
              <h3>
                {MONTHS[m - 1]} {y}
              </h3>
              <div className="cal-grid">
                {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((d, i) => (
                  <span className="dow" key={i}>
                    {d}
                  </span>
                ))}
                {cells.map((d, i) => {
                  if (d === null) return <span key={i} />;
                  const key = `${mo}-${String(d).padStart(2, '0')}`;
                  const entries = byDate[key] || [];
                  const active = entries.length > 0;
                  const isLatest = key === latestDate;
                  return (
                    <span className="cell" key={i}>
                      <button
                        className={`day${active ? ' active' : ''}${isLatest ? ' latest' : ''}`}
                        disabled={!active}
                        onClick={() => dayClick(key, entries)}
                        aria-label={active ? `${key}: ${entries.map((e) => KIND_LABEL[e.kind]).join(', ')}` : key}
                      >
                        <span className="num">{d}</span>
                        {active && (
                          <span className="marks">
                            {entries.map((e) => (
                              <i key={e.kind} className={`mark ${e.kind}`}>
                                {KIND_MARK[e.kind]}
                              </i>
                            ))}
                          </span>
                        )}
                      </button>
                      {active && (
                        <span className="peek">{entries.map((e) => KIND_LABEL[e.kind]).join(' + ')}</span>
                      )}
                      {open === key && (
                        <span className="pop">
                          {entries.map((e) => (
                            <button key={e.slug} onClick={() => router.push(`/${vertical}/r/${e.slug}`)}>
                              {KIND_LABEL[e.kind]}
                            </button>
                          ))}
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
