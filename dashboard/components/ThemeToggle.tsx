'use client';

import { useEffect, useState } from 'react';

function effective(): 'dark' | 'light' {
  const c = document.documentElement.classList;
  if (c.contains('dark')) return 'dark';
  if (c.contains('light')) return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export default function ThemeToggle() {
  const [mode, setMode] = useState<'dark' | 'light' | null>(null);

  useEffect(() => setMode(effective()), []);

  function toggle() {
    const next = effective() === 'dark' ? 'light' : 'dark';
    const el = document.documentElement.classList;
    el.remove('dark', 'light');
    el.add(next);
    try {
      localStorage.setItem('theme', next);
    } catch {}
    setMode(next);
  }

  return (
    <button
      className="theme-toggle"
      onClick={toggle}
      aria-label={mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      title="Toggle light / dark"
    >
      {mode === null ? '◐' : mode === 'dark' ? '☀' : '☾'}
    </button>
  );
}
