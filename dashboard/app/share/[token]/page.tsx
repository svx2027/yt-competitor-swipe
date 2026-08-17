import { verifyShareToken } from '@/lib/share';
import { getReport } from '@/lib/content';
import { VERTICALS } from '@/lib/verticals';
import ReportView from '@/components/ReportView';
import ThemeToggle from '@/components/ThemeToggle';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Shared report' };

export default async function SharePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const v = await verifyShareToken(decodeURIComponent(token));
  const report = v ? getReport(v.vertical, v.slug) : null;

  if (!v || !report) {
    return (
      <div className="wrap center">
        <div className="card login">
          <div className="brand big">Client Intelligence</div>
          <h1>Link expired or invalid</h1>
          <p className="muted">Ask for a fresh share link.</p>
        </div>
      </div>
    );
  }

  const exp = v.exp ? new Date(v.exp * 1000).toUTCString().slice(0, 16) : '';
  const entry = VERTICALS[v.vertical];

  return (
    <div className="wrap" data-vertical={v.vertical}>
      <span className="login-toggle">
        <ThemeToggle />
      </span>
      <div className="banner info">
        Shared read-only report{exp ? ` · link valid until ${exp}` : ''}
      </div>
      <ReportView report={report} shared takeLabel={entry.takeLabel} vertical={v.vertical} />
    </div>
  );
}
