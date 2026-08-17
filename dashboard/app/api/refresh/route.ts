import { auth } from '@/lib/auth';
import { getManifest } from '@/lib/content';
import { reconcile } from '@/lib/reconcile';
import { VERTICAL_LIST } from '@/lib/verticals';

export const runtime = 'nodejs';
export const maxDuration = 60;

// Per-vertical summary, one entry per registered vertical (null when that vertical
// has no ingested content yet, e.g. a pending vertical or one mid-rollout).
function status() {
  const verticals: Record<string, unknown> = {};
  for (const v of VERTICAL_LIST) {
    const m = getManifest(v.slug);
    verticals[v.slug] = m
      ? {
          generatedAt: m.generatedAt,
          latestSlug: m.latestSlug,
          latestDate: m.latestDate,
          reportCount: m.reports.length,
          dayCount: Object.keys(m.byDate).length,
        }
      : null;
  }
  return { verticals };
}

// Admin-only, same as POST: status() reports every vertical's report metadata in one
// payload, so a client session must never reach it, only its own vertical's data is
// meant to be visible to a client (enforced everywhere else via session.user.vertical,
// but this endpoint has no per-vertical scoping, so the whole payload is admin-only
// rather than trying to filter it down to one vertical for a hypothetical client caller
// that does not exist today, see RefreshStatus.tsx, which never calls GET).
export async function GET() {
  const session = await auth();
  if (!session?.user) return Response.json({ error: 'unauthorized' }, { status: 401 });
  if (session.user.role !== 'admin') return Response.json({ error: 'unauthorized' }, { status: 401 });
  return Response.json({ ...status(), configured: !!process.env.GITHUB_TOKEN });
}

// Human-triggered reconcile: the Refresh button. Admin-only: reconcile pulls report
// .md files that live only on claude/* run branches onto main (each PUT -> a commit ->
// a Vercel rebuild), which is an operational action, not something individual clients
// should be able to trigger. Shares reconcile() with the cron path (app/api/reconcile).
export async function POST() {
  const session = await auth();
  if (!session?.user) return Response.json({ error: 'unauthorized' }, { status: 401 });
  if (session.user.role !== 'admin') return Response.json({ error: 'unauthorized' }, { status: 401 });

  const token = process.env.GITHUB_TOKEN;
  if (!token) return Response.json({ configured: false, ...status() });

  const result = await reconcile(token);
  if (result.error) {
    return Response.json({ configured: true, error: result.error }, { status: result.status ?? 500 });
  }
  return Response.json({ configured: true, ...result, ...status() });
}
