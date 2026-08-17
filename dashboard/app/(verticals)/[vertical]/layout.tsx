import { notFound } from 'next/navigation';
import { auth } from '@/lib/auth';
import { canAccessVertical, isVerticalSlug } from '@/lib/verticals';

// Defense in depth: middleware already blocks a client session from reaching another
// vertical's routes, but the middleware matcher exclusions are prefix based, so a
// future regression there (a widened exclusion, a new route added outside the
// matcher's coverage) could bypass that check without anyone noticing. This layout
// re-derives the session and re-checks vertical ownership independently, so a
// middleware gap alone is never enough to leak cross-vertical data.
export default async function VerticalLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ vertical: string }>;
}) {
  const { vertical } = await params;
  if (!isVerticalSlug(vertical)) notFound();

  const session = await auth();
  if (!canAccessVertical(session, vertical)) notFound();

  // The key-date countdown chip (components/KeyDateCountdown.tsx) and the admin vertical
  // switcher render inside each page's own topbar markup (page.tsx, r/[slug]/page.tsx)
  // rather than here, since the topbar itself lives in those files, not in this
  // wrapper. This div is what makes `vertical` resolvable via [data-vertical] in
  // globals.css for every page under it, including those two.
  return <div data-vertical={vertical}>{children}</div>;
}
