'use client';

import { useState } from 'react';

function relative(iso: string) {
  const then = new Date(iso).getTime();
  if (!then) return '';
  const s = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (s < 90) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hr ago`;
  const d = Math.round(h / 24);
  return `${d} day${d > 1 ? 's' : ''} ago`;
}

export default function RefreshStatus({
  generatedAt,
  latestDate,
  canRefresh = true,
}: {
  generatedAt: string | null;
  latestDate: string | null;
  canRefresh?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [tone, setTone] = useState<'ok' | 'work' | 'err'>('ok');

  async function refresh() {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch('/api/refresh', { method: 'POST' });
      const j = await r.json();
      if (j.error) {
        setTone('err');
        setMsg('Refresh failed. Try again.');
      } else if (j.configured === false) {
        setTone('err');
        setMsg('Refresh not set up yet.');
      } else if (j.rebuilding) {
        setTone('work');
        setMsg(`Pulled ${j.recovered.length} missing report${j.recovered.length > 1 ? 's' : ''}, rebuilding, reload in ~2 min.`);
      } else {
        setTone('ok');
        setMsg('Up to date ✓');
      }
    } catch {
      setTone('err');
      setMsg('Refresh failed. Try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="refresh">
      {canRefresh && (
        <button className="btn refresh-btn" onClick={refresh} disabled={busy} title="Check for and pull the latest reports">
          <span className={`refresh-icon${busy ? ' spin' : ''}`} aria-hidden="true">↻</span>
          {busy ? 'Refreshing…' : 'Refresh'}
        </button>
      )}
      <span className={`refresh-note ${tone}`}>
        {msg ||
          (generatedAt
            ? latestDate
              ? `Latest ${latestDate} · updated ${relative(generatedAt)}`
              : `Updated ${relative(generatedAt)}`
            : 'No reports yet')}
      </span>
    </span>
  );
}
