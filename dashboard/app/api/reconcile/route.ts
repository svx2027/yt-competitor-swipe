import crypto from 'node:crypto';
import { reconcile } from '@/lib/reconcile';

// Machine-triggered reconcile for Vercel Cron (see dashboard/vercel.json).
// Vercel Cron issues a GET and injects `Authorization: Bearer <CRON_SECRET>`.
// This closes the delivery loop with no human: the daily/weekly/monthly cloud
// routine strands its report on a claude/* branch; this pulls it onto main a few
// minutes later, which auto-triggers the dashboard rebuild.
//
// The human-facing counterpart is app/api/refresh (POST, session-gated). Both call
// the same reconcile() so behavior is identical.

export const runtime = 'nodejs';
export const maxDuration = 60;
export const dynamic = 'force-dynamic';

// Constant-time compare so a mismatched CRON_SECRET can't be brute-forced via response
// timing. Guards the length mismatch first: crypto.timingSafeEqual throws (rather than
// returning false) when its two buffers differ in length, and an attacker-controlled
// header must never be able to trigger a thrown error here, only a clean 401.
function timingSafeEqualStrings(a: string, b: string): boolean {
  const bufA = Buffer.from(a, 'utf8');
  const bufB = Buffer.from(b, 'utf8');
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

export async function GET(req: Request) {
  const secret = process.env.CRON_SECRET;
  // Fail CLOSED: with no secret configured the endpoint must not run, or it would
  // be an unauthenticated write-to-main path open to the internet.
  if (!secret) {
    return Response.json({ error: 'CRON_SECRET not configured' }, { status: 503 });
  }
  const header = req.headers.get('authorization') || '';
  if (!timingSafeEqualStrings(header, `Bearer ${secret}`)) {
    return Response.json({ error: 'unauthorized' }, { status: 401 });
  }

  const token = process.env.GITHUB_TOKEN;
  // Fail LOUD on the cron path: a missing/mis-scoped token must surface as a failed
  // Vercel run, not a 200 that reads as success and no-ops forever. (The human Refresh
  // path keeps returning 200 configured:false to drive its "not set up yet" UI.)
  if (!token) return Response.json({ configured: false }, { status: 503 });

  const result = await reconcile(token);
  const httpStatus = result.error ? (result.status ?? 500) : 200;
  return Response.json({ configured: true, ...result }, { status: httpStatus });
}
