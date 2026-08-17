'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

// No existing keyboard-handling pattern elsewhere in the dashboard (checked before
// adding this), so this establishes the convention: vim-style j = next, k = previous.
export default function ReportKeyNav({ prevHref, nextHref }: { prevHref: string | null; nextHref: string | null }) {
  const router = useRouter();

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable) return;

      if (e.key === 'j' && nextHref) {
        e.preventDefault();
        router.push(nextHref);
      } else if (e.key === 'k' && prevHref) {
        e.preventDefault();
        router.push(prevHref);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [prevHref, nextHref, router]);

  return null;
}
