import { notFound } from 'next/navigation';
import Link from 'next/link';
import { auth, signOut } from '@/lib/auth';
import { canAccessVertical, isVerticalSlug, VERTICALS } from '@/lib/verticals';
import {
  getCompetitorRegistry,
  getCompetitorWindow,
  getCombined,
  latestWindowKey,
  windowsWithYears,
  type CompetitorEntry,
  type RadarRow,
} from '@/lib/competitors';
import ThemeToggle from '@/components/ThemeToggle';
import CompetitorExplorer, { type Filters } from '@/components/CompetitorExplorer';

const str = (v: string | string[] | undefined) => (typeof v === 'string' ? v : '');

export async function generateMetadata({ params }: { params: Promise<{ vertical: string }> }) {
  const { vertical } = await params;
  if (!isVerticalSlug(vertical)) return {};
  if (!canAccessVertical(await auth(), vertical)) return {};
  return { title: `${VERTICALS[vertical].name} · Competitor Radar` };
}

export default async function CompetitorRadarPage({
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

  const sp = await searchParams;
  const cParam = str(sp.c);
  const wParam = str(sp.w);

  const competitor: CompetitorEntry =
    registry.competitors.find((c) => c.slug === cParam) || registry.competitors[0];
  const years = windowsWithYears(competitor); // oldest-first [{key, year}]
  const multiWindow = years.length > 1;

  // Mode: combined ("Both years") only when there are >= 2 windows; else a single window.
  const combinedMode = wParam === 'combined' && multiWindow;

  let rows: RadarRow[];
  let combined = false;
  let activeKey: string; // for the switcher's active state: a window key or "combined"
  let windowLabel: string;
  let total: number;

  if (combinedMode) {
    const c = getCombined(vertical, competitor);
    if (!c) notFound();
    rows = c.rows;
    combined = true;
    activeKey = 'combined';
    windowLabel = 'Both years';
    total = c.total;
  } else {
    const windowKey =
      (wParam && competitor.windows.includes(wParam) ? wParam : null) || latestWindowKey(competitor);
    const data = windowKey ? getCompetitorWindow(vertical, competitor.slug, windowKey) : null;
    if (!data || !windowKey) notFound();
    rows = data.rows;
    activeKey = windowKey;
    windowLabel = data.window.label;
    total = data.counts.total;
  }

  const initial: Filters = {
    fmt: str(sp.fmt),
    subj: str(sp.subj),
    mon: str(sp.mon),
    tier: str(sp.tier),
    q: str(sp.q),
  };

  const signOutButton = (
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
  );

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
          {signOutButton}
        </div>
      </header>

      <nav className="crumb">
        <Link href={`/${vertical}`} className="btn text">
          ← Reports
        </Link>
      </nav>

      <section className="radar-hero">
        <div className="radar-hero-title">
          <h1>Competitor Radar</h1>
          <p className="muted">What is working for {competitor.name}. Dated for us.</p>
        </div>
        <div className="radar-pickers">
          {multiWindow && (
            <div className="radar-picker" role="group" aria-label="Cycle year">
              {years.map((y) => (
                <Link
                  key={y.key}
                  href={`${base}?c=${competitor.slug}&w=${y.key}`}
                  className={`radar-chip lg${activeKey === y.key ? ' on' : ''}`}
                  aria-current={activeKey === y.key ? 'true' : undefined}
                >
                  Cycle {y.year}
                </Link>
              ))}
              <Link
                href={`${base}?c=${competitor.slug}&w=combined`}
                className={`radar-chip lg${combined ? ' on' : ''}`}
                aria-current={combined ? 'true' : undefined}
              >
                Both years
              </Link>
            </div>
          )}
          {!multiWindow && <span className="chip">{windowLabel}</span>}
          {competitor.hasInsights && (
            <Link className="radar-chip lg radar-insights-link" href={`${base}/insights`}>
              Insights →
            </Link>
          )}
        </div>
      </section>

      {combined && (
        <p className="radar-agenote muted">
          Both years shown together and ranked by outlier multiple (views vs that year&apos;s own format median), which is
          age-fair: 2024 videos have had far longer to collect views, so raw view counts are not comparable across years.
        </p>
      )}

      <CompetitorExplorer rows={rows} combined={combined} initial={initial} />

      <footer className="foot">
        {competitor.name} ({competitor.handle}) · {total} videos · {windowLabel} · source: competitor research pipeline
      </footer>
    </div>
  );
}
