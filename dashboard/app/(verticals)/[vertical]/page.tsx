import { notFound } from 'next/navigation';
import Link from 'next/link';
import { auth, signOut } from '@/lib/auth';
import { getManifest, getReport, KIND_LABEL } from '@/lib/content';
import { canAccessVertical, isVerticalSlug, VERTICALS } from '@/lib/verticals';
import { nextRunText } from '@/lib/schedule';
import Calendar from '@/components/Calendar';
import ReportView from '@/components/ReportView';
import ShareButton from '@/components/ShareButton';
import RefreshStatus from '@/components/RefreshStatus';
import ThemeToggle from '@/components/ThemeToggle';
import KeyDateCountdown from '@/components/KeyDateCountdown';
import VerticalSwitcher from '@/components/VerticalSwitcher';
import CompetitorRadarCard from '@/components/CompetitorRadarCard';
import { getCompetitorRegistry, getCompetitorWindow, latestWindowKey, windowsWithYears } from '@/lib/competitors';

export async function generateMetadata({ params }: { params: Promise<{ vertical: string }> }) {
  const { vertical } = await params;
  if (!isVerticalSlug(vertical)) return {};
  // Gated the same as the layout's notFound() check: a mismatched-vertical request
  // must not learn the vertical's display name through the page <title>, even though
  // the layout below already blocks the rendered body.
  if (!canAccessVertical(await auth(), vertical)) return {};
  return { title: `${VERTICALS[vertical].name} Intelligence` };
}

const RadarIcon = () => (
  <svg viewBox="0 0 48 48" width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="24" cy="24" r="17" opacity="0.35" />
    <circle cx="24" cy="24" r="10.5" opacity="0.6" />
    <circle cx="24" cy="24" r="2.2" fill="currentColor" stroke="none" />
    <path d="M24 24 L35 13" opacity="0.9" />
  </svg>
);

export default async function VerticalHome({ params }: { params: Promise<{ vertical: string }> }) {
  const { vertical } = await params;
  if (!isVerticalSlug(vertical)) notFound();
  const entry = VERTICALS[vertical];
  const session = await auth();
  const isAdmin = session?.user?.role === 'admin';
  // Pending verticals have no ingested content yet; a "live" vertical whose pipeline
  // hasn't produced its first report yet (e.g. mid-rollout) falls back the same way
  // instead of throwing, so this page never hard-crashes on a content gap.
  const manifest = entry.status === 'live' ? getManifest(vertical) : null;

  const brand = (
    <Link className="brand" href={`/${vertical}`}>
      <span>{entry.name}</span> Intelligence
    </Link>
  );

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

  if (!manifest) {
    return (
      <div className="wrap">
        <header className="topbar">
          <div className="topbar-left">
            {brand}
            <KeyDateCountdown vertical={vertical} />
            {isAdmin && <RefreshStatus generatedAt={null} latestDate={null} canRefresh={isAdmin} />}
          </div>
          <div className="topbar-right">
            {isAdmin && <VerticalSwitcher current={vertical} />}
            <ThemeToggle />
            <span className="user">{session?.user?.email ?? session?.user?.name}</span>
            {signOutButton}
          </div>
        </header>

        <section className="empty-state">
          <div className="empty-state-icon">
            <RadarIcon />
          </div>
          {entry.pendingCopy ? (
            <>
              <h2>{entry.pendingCopy.headline}</h2>
              <p className="muted">{entry.pendingCopy.body}</p>
              <span className="chip">Launching soon</span>
            </>
          ) : (
            <>
              <h2>{entry.name} reports are on their way.</h2>
              <p className="muted">No {entry.name} reports have been published yet. Check back after the next scheduled run.</p>
            </>
          )}
        </section>
      </div>
    );
  }

  const latest = manifest.latestSlug ? getReport(vertical, manifest.latestSlug) : null;
  const warnings = manifest.issues.filter((i: any) => i.level === 'warning');
  const held = manifest.issues.filter((i: any) => i.level === 'held');
  const nextRun = nextRunText(vertical);

  // Competitor Radar entry card: shown only when this vertical has competitor data.
  // Additive to the existing home; verticals without a registry render exactly as before.
  const radarRegistry = getCompetitorRegistry(vertical);
  let radarSummary:
    | { name: string; videos: number; breakouts: number; windowLabel: string; cyclesLabel?: string }
    | null = null;
  if (radarRegistry) {
    const comp = radarRegistry.competitors[0];
    const win = comp ? latestWindowKey(comp) : null;
    const data = comp && win ? getCompetitorWindow(vertical, comp.slug, win) : null;
    if (comp && data) {
      const yrs = windowsWithYears(comp).map((w) => w.year);
      radarSummary = {
        name: comp.name,
        videos: data.counts.total,
        breakouts: data.rows.filter((r) => (r.mult ?? 0) >= 5).length,
        windowLabel: data.window.label,
        cyclesLabel: yrs.length > 1 ? `${yrs.length} cycles: ${yrs.join(' + ')}` : undefined,
      };
    }
  }

  return (
    <div className="wrap">
      <header className="topbar">
        <div className="topbar-left">
          {brand}
          <KeyDateCountdown vertical={vertical} />
          <RefreshStatus generatedAt={manifest.generatedAt} latestDate={manifest.latestDate} canRefresh={isAdmin} />
        </div>
        <div className="topbar-right">
          {isAdmin && <VerticalSwitcher current={vertical} />}
          <ThemeToggle />
          <span className="user">{session?.user?.email ?? session?.user?.name}</span>
          {signOutButton}
        </div>
      </header>

      {held.length > 0 && (
        <div className="banner hold">
          <strong>{held.length} report(s) held by the verification gate</strong>, not published until fixed:
          <ul>
            {held.map((i: any, n: number) => (
              <li key={n}>
                {i.slug}: {i.msg}
              </li>
            ))}
          </ul>
        </div>
      )}
      {warnings.length > 0 && (
        <div className="banner warn">
          <strong>Verification notes</strong>
          <ul>
            {warnings.map((i: any, n: number) => (
              <li key={n}>
                {i.slug}: {i.msg}
              </li>
            ))}
          </ul>
        </div>
      )}

      {radarSummary && (
        <CompetitorRadarCard
          vertical={vertical}
          name={radarSummary.name}
          videos={radarSummary.videos}
          breakouts={radarSummary.breakouts}
          windowLabel={radarSummary.windowLabel}
          cyclesLabel={radarSummary.cyclesLabel}
        />
      )}

      <section className="panel">
        <Calendar byDate={manifest.byDate} latestDate={manifest.latestDate} vertical={vertical} />
      </section>

      {latest && (
        <section className="latest">
          <div className="section-head">
            <h2>
              Latest · {KIND_LABEL[latest.kind]} · {latest.date}
            </h2>
            <ShareButton slug={latest.slug} vertical={vertical} />
          </div>
          <ReportView report={latest} takeLabel={entry.takeLabel} vertical={vertical} />
        </section>
      )}

      <footer className="foot">
        Rebuilt {String(manifest.generatedAt).slice(0, 16).replace('T', ' ')} UTC · ledger {manifest.historyRows} rows ·{' '}
        {manifest.reports.length} reports published{nextRun ? ` · ${nextRun}` : ''}
      </footer>
    </div>
  );
}
