import Link from 'next/link';

// Entry point to the Competitor Radar, shown on the vertical home above the reports.
// Presentational only: the home page loads the summary and passes it in, so this card
// renders nothing (and the home page omits it) when a vertical has no competitor data.
export default function CompetitorRadarCard({
  vertical,
  name,
  videos,
  breakouts,
  windowLabel,
  cyclesLabel,
}: {
  vertical: string;
  name: string;
  videos: number;
  breakouts: number;
  windowLabel: string;
  cyclesLabel?: string;
}) {
  return (
    <Link className="radar-card" href={`/${vertical}/competitors`} aria-label={`Open the Competitor Radar for ${name}`}>
      <span className="radar-card-icon" aria-hidden="true">
        <svg viewBox="0 0 48 48" width="30" height="30" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="24" cy="24" r="17" opacity="0.35" />
          <circle cx="24" cy="24" r="10.5" opacity="0.6" />
          <circle cx="24" cy="24" r="2.2" fill="currentColor" stroke="none" />
          <path d="M24 24 L35 13" opacity="0.9" />
        </svg>
      </span>
      <span className="radar-card-body">
        <span className="radar-card-title">Competitor Radar</span>
        <span className="radar-card-desc">What worked for {name}, mapped to the active seasonal calendar.</span>
        <span className="radar-card-stats">
          <b>{videos.toLocaleString('en-IN')}</b> videos analysed
          <span className="radar-dot">·</span>
          <b>{breakouts}</b> breakouts 5x+
          <span className="radar-dot">·</span>
          {cyclesLabel ?? windowLabel}
        </span>
      </span>
      <span className="radar-card-go" aria-hidden="true">
        Open radar →
      </span>
    </Link>
  );
}
