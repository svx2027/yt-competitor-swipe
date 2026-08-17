import type { VerticalSlug } from './verticals';

// Known automated daily-routine run times, IST (fixed UTC+5:30, no DST, same
// convention the Python pipeline itself uses). Only fitness has a live scheduled
// routine today; outdoors is intentionally absent so the freshness footer omits
// a next-run line for it rather than showing a fabricated time.
// Designer-owned display data, not the source of truth for the routines
// themselves, hardcoded per the multi-vertical task spec.
const DAILY_ROUTINE_UTC: Partial<Record<VerticalSlug, { hour: number; minute: number; istLabel: string }>> = {
  fitness: { hour: 3, minute: 30, istLabel: '09:00 IST' }, // 09:00 IST
};

/** "next run in ~Xh Ym (09:00 IST)", or null when this vertical has no known routine. */
export function nextRunText(vertical: VerticalSlug, now: Date = new Date()): string | null {
  const sched = DAILY_ROUTINE_UTC[vertical];
  if (!sched) return null;

  const next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), sched.hour, sched.minute, 0));
  if (next.getTime() <= now.getTime()) next.setUTCDate(next.getUTCDate() + 1);

  const deltaMs = next.getTime() - now.getTime();
  const hrs = Math.floor(deltaMs / 3_600_000);
  const mins = Math.round((deltaMs % 3_600_000) / 60_000);
  const parts = hrs > 0 ? [`${hrs}h`, `${mins}m`] : [`${mins}m`];
  return `next run in ~${parts.join(' ')} (${sched.istLabel})`;
}
