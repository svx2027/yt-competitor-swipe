import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { DEFAULT_VERTICAL, isVerticalSlug } from '@/lib/verticals';

export default auth((req) => {
  const { nextUrl } = req;

  if (!req.auth) {
    const login = new URL('/login', nextUrl.origin);
    return NextResponse.redirect(login);
  }

  const role = req.auth.user?.role;
  const vertical = req.auth.user?.vertical;
  const isAdmin = role === 'admin';

  // Authenticated on the bare home route: send them straight into their vertical.
  // Admin has no home vertical of its own, so land on fitness, the default vertical.
  if (nextUrl.pathname === '/') {
    if (isAdmin) {
      return NextResponse.redirect(new URL(`/${DEFAULT_VERTICAL}`, nextUrl.origin));
    }
    if (isVerticalSlug(vertical)) {
      return NextResponse.redirect(new URL(`/${vertical}`, nextUrl.origin));
    }
    // No usable vertical claim on the session (should not normally happen). Back to
    // login rather than looping on `/`.
    return NextResponse.redirect(new URL('/login', nextUrl.origin));
  }

  // Authenticated but hitting a different vertical's route: never reveal that the
  // route exists. Render the generic not-found page at the original URL instead of
  // redirecting, so a client probing another vertical's slugs cannot distinguish
  // "wrong vertical" from "no such report".
  // The 404 status has to be set explicitly: rewrite() swaps the body but keeps
  // the original status, which served the not-found PAGE with a 200. That alone
  // was an enumeration signal, since a real-but-foreign vertical answered 200
  // while a nonexistent path answered 404, telling a client exactly which other
  // verticals exist on the platform.
  const firstSegment = nextUrl.pathname.split('/')[1];
  if (isVerticalSlug(firstSegment) && !isAdmin && vertical !== firstSegment) {
    return NextResponse.rewrite(new URL('/404', nextUrl.origin), { status: 404 });
  }
});

export const config = {
  // api/reconcile is the cron endpoint, it authenticates via CRON_SECRET Bearer, not
  // a session, so it must bypass this auth-redirect middleware (else the cron GET is
  // 307'd to /login before the handler runs). api/refresh stays gated: the button is
  // only ever clicked by a logged-in user.
  //
  // Each exclusion is anchored to a full path segment (a trailing "/" or end-of-string
  // after the literal), not a bare string prefix: a plain "login" would also exclude a
  // hypothetical future "/login-recovery" page, silently making it public. Verified
  // against every route in app/ today; none collides with a reserved prefix.
  matcher: [
    '/((?!api/auth(?:/|$)|api/reconcile(?:/|$)|login(?:/|$)|share/|_next/static/|_next/image|favicon\\.ico$|robots\\.txt$).*)',
  ],
};
