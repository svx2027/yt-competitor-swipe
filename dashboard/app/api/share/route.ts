import { auth } from '@/lib/auth';
import { getReport } from '@/lib/content';
import { createShareToken } from '@/lib/share';
import { isVerticalSlug, type VerticalSlug } from '@/lib/verticals';

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user) {
    return Response.json({ error: 'unauthorized' }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const slug = typeof body.slug === 'string' ? body.slug : '';
  const days = Math.min(365, Math.max(1, Math.round(Number(body.days) || 7)));
  const requestedVertical = typeof body.vertical === 'string' ? body.vertical : undefined;
  const role = session.user.role;
  const sessionVertical = session.user.vertical;

  let vertical: VerticalSlug;
  if (role === 'admin') {
    // Admin may mint a link for any vertical; default to fitness when the caller omitted one.
    if (requestedVertical !== undefined && !isVerticalSlug(requestedVertical)) {
      return Response.json({ error: 'unknown vertical' }, { status: 400 });
    }
    vertical = requestedVertical ?? 'fitness';
  } else {
    // A client session may only mint a link for its own vertical. A mismatched
    // `vertical` in the body is rejected outright rather than silently overridden, so
    // a tampered client request fails loudly instead of leaking cross-vertical access.
    if (!isVerticalSlug(sessionVertical)) {
      return Response.json({ error: 'unauthorized' }, { status: 401 });
    }
    if (requestedVertical !== undefined && requestedVertical !== sessionVertical) {
      return Response.json({ error: 'vertical mismatch' }, { status: 403 });
    }
    vertical = sessionVertical;
  }

  if (!slug || !getReport(vertical, slug)) {
    return Response.json({ error: 'unknown report' }, { status: 400 });
  }

  const token = await createShareToken(slug, vertical, days);
  const url = new URL(`/share/${token}`, req.url).toString();
  return Response.json({ url, days, vertical });
}
