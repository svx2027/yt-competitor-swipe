import Link from 'next/link';
import { notFound } from 'next/navigation';
import { auth } from '@/lib/auth';
import { getManifest, getReport, siblingNav, KIND_LABEL } from '@/lib/content';
import { canAccessVertical, isVerticalSlug, VERTICALS, VERTICAL_LIST } from '@/lib/verticals';
import ReportView from '@/components/ReportView';
import ShareButton from '@/components/ShareButton';
import ThemeToggle from '@/components/ThemeToggle';
import KeyDateCountdown from '@/components/KeyDateCountdown';
import VerticalSwitcher from '@/components/VerticalSwitcher';
import ReportKeyNav from '@/components/ReportKeyNav';

export function generateStaticParams() {
  return VERTICAL_LIST.flatMap((v) => {
    const manifest = getManifest(v.slug);
    return manifest ? manifest.reports.map((r: any) => ({ vertical: v.slug, slug: r.slug })) : [];
  });
}
export const dynamicParams = false;

export async function generateMetadata({ params }: { params: Promise<{ vertical: string; slug: string }> }) {
  const { vertical, slug } = await params;
  if (!isVerticalSlug(vertical)) return {};
  // Gated the same as the layout's notFound() check, and before the report is even
  // read: a mismatched-vertical request must not learn the report's kind, date, or
  // the vertical's display name through the page <title>.
  if (!canAccessVertical(await auth(), vertical)) return {};
  const entry = VERTICALS[vertical];
  const report = getReport(vertical, slug);
  return { title: report ? `${KIND_LABEL[report.kind]} · ${report.date} · ${entry.name} Intelligence` : `${entry.name} Intelligence` };
}

export default async function ReportPage({
  params,
}: {
  params: Promise<{ vertical: string; slug: string }>;
}) {
  const { vertical, slug } = await params;
  if (!isVerticalSlug(vertical)) notFound();
  const entry = VERTICALS[vertical];
  const session = await auth();
  const isAdmin = session?.user?.role === 'admin';
  const manifest = getManifest(vertical);
  const report = getReport(vertical, slug);
  if (!manifest || !report) notFound();
  const nav = siblingNav(manifest, slug);
  const prevHref = nav.prev ? `/${vertical}/r/${nav.prev.slug}` : null;
  const nextHref = nav.next ? `/${vertical}/r/${nav.next.slug}` : null;

  return (
    <div className="wrap">
      <ReportKeyNav prevHref={prevHref} nextHref={nextHref} />
      <header className="topbar">
        <div className="topbar-left">
          <Link className="brand" href={`/${vertical}`}>
            <span>{entry.name}</span> Intelligence
          </Link>
          <KeyDateCountdown vertical={vertical} />
        </div>
        <div className="topbar-right">
          {isAdmin && <VerticalSwitcher current={vertical} />}
          <ThemeToggle />
          <ShareButton slug={slug} vertical={vertical} />
        </div>
      </header>

      <nav className="repnav">
        <span>{prevHref ? <Link href={prevHref} title="Previous report (k)">← {nav.prev.date}</Link> : null}</span>
        <span className="repnav-mid">
          <strong>
            {KIND_LABEL[report.kind]} · {report.date}
          </strong>
          {nav.sameDay.map((s: any) => (
            <Link key={s.slug} className="chip link" href={`/${vertical}/r/${s.slug}`}>
              {KIND_LABEL[s.kind]} of this day
            </Link>
          ))}
        </span>
        <span>{nextHref ? <Link href={nextHref} title="Next report (j)">{nav.next.date} →</Link> : null}</span>
      </nav>

      <ReportView report={report} takeLabel={entry.takeLabel} vertical={vertical} />
    </div>
  );
}
