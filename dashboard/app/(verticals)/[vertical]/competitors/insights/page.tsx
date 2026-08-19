import { notFound } from 'next/navigation';
import Link from 'next/link';
import { auth, signOut } from '@/lib/auth';
import { canAccessVertical, isVerticalSlug, VERTICALS } from '@/lib/verticals';
import { getCompetitorRegistry, getInsights } from '@/lib/competitors';
import ThemeToggle from '@/components/ThemeToggle';
import InsightsView from '@/components/InsightsView';

const str = (v: string | string[] | undefined) => (typeof v === 'string' ? v : '');

export async function generateMetadata({ params }: { params: Promise<{ vertical: string }> }) {
  const { vertical } = await params;
  if (!isVerticalSlug(vertical)) return {};
  if (!canAccessVertical(await auth(), vertical)) return {};
  return { title: `${VERTICALS[vertical].name} · Radar Insights` };
}

export default async function InsightsPage({
  params,
  searchParams,
}: {
  params: Promise<{ vertical: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { vertical } = await params;
  if (!isVerticalSlug(vertical)) notFound();
  const session = await auth();
  if (!canAccessVertical(session, vertical)) notFound();

  const registry = getCompetitorRegistry(vertical);
  if (!registry) notFound();
  const competitor = registry.competitors[0];
  const insights = getInsights(vertical, competitor.slug);
  if (!insights) notFound();

  const sp = await searchParams;
  const m = str(sp.m);

  const base = `/${vertical}/competitors`;

  return (
    <div className="wrap">
      <header className="topbar">
        <div className="topbar-left">
          <Link className="brand" href={`/${vertical}`}>
            <span>{VERTICALS[vertical].name}</span> Intelligence
          </Link>
        </div>
        <div className="topbar-right">
          <ThemeToggle />
          <span className="user">{session?.user?.email ?? session?.user?.name}</span>
          <form
            action={async () => {
              'use server';
              await signOut({ redirectTo: '/login' });
            }}
          >
            <button className="btn ghost" type="submit">
              Sign out
            </button>
          </form>
        </div>
      </header>

      <nav className="crumb">
        <Link href={base} className="btn text">
          ← Radar
        </Link>
      </nav>

      <section className="radar-hero">
        <div className="radar-hero-title">
          <h1>Radar Insights</h1>
          <p className="muted">
            What worked for {insights.competitor_name} across {insights.years.join(' and ')}, month by month, dated for
            the upcoming cycle.
          </p>
        </div>
      </section>

      <InsightsView data={insights} initialMonth={m} />
    </div>
  );
}
