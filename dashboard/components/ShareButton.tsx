'use client';

import { useState } from 'react';
import type { VerticalSlug } from '@/lib/verticals';

const PRESETS = [1, 7, 30, 90];

export default function ShareButton({ slug, vertical }: { slug: string; vertical: VerticalSlug }) {
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState(7);
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  async function create() {
    setBusy(true);
    setError('');
    setCopied(false);
    try {
      const r = await fetch('/api/share', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ slug, vertical, days }),
      });
      const j = await r.json();
      if (j.url) setUrl(j.url);
      else setError(j.error || 'Could not create link');
    } catch {
      setError('Could not create link');
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setError('Copy failed, select and copy manually');
    }
  }

  return (
    <span className="share">
      <button className="btn" onClick={() => setOpen(!open)}>
        Share
      </button>
      {open && (
        <span className="share-panel">
          <span className="share-row">
            <span className="share-label">Valid for</span>
            {PRESETS.map((p) => (
              <button key={p} className={`chip pick-days${days === p ? ' on' : ''}`} onClick={() => setDays(p)}>
                {p}d
              </button>
            ))}
            <input
              type="number"
              min={1}
              max={365}
              value={days}
              onChange={(e) => setDays(Math.min(365, Math.max(1, +e.target.value || 1)))}
            />
            <span className="share-label">days</span>
          </span>
          <span className="share-row">
            <button className="btn primary" onClick={create} disabled={busy}>
              {busy ? 'Creating…' : 'Create link'}
            </button>
            {url && (
              <>
                <input className="share-url" readOnly value={url} onFocus={(e) => e.target.select()} />
                <button className="btn" onClick={copy}>
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </>
            )}
          </span>
          {error && <span className="err small">{error}</span>}
          <span className="share-note">Anyone with the link sees only this report until it expires.</span>
        </span>
      )}
    </span>
  );
}
