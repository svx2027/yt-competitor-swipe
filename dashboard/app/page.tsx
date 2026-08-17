import { redirect } from 'next/navigation';
import { auth } from '@/lib/auth';
import { DEFAULT_VERTICAL, isVerticalSlug } from '@/lib/verticals';

// Middleware normally rewrites the authenticated `/` request straight to `/VERTICAL`
// before Next.js ever renders this page. This is a server-side fallback for a request
// that reaches the App Router without passing through middleware first (for example a
// prefetch or an internal RSC fetch), so a direct hit on `/` never dead-ends.
export default async function RootPage() {
  const session = await auth();
  if (!session?.user) redirect('/login');
  if (session.user.role === 'admin') redirect(`/${DEFAULT_VERTICAL}`);
  if (isVerticalSlug(session.user.vertical)) redirect(`/${session.user.vertical}`);
  redirect('/login');
}
