// Skeleton shown while the radar page's server component resolves. Mirrors the real
// layout order (hero, then the KPI/filter/table block) so nothing jumps on load.
export default function Loading() {
  return (
    <div className="wrap">
      <div className="topbar">
        <div className="sk sk-brand" />
        <div className="sk sk-btn" />
      </div>
      <div className="radar-hero">
        <div className="sk sk-h1" />
      </div>
      <div className="radar-kpis">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="sk sk-kpi" />
        ))}
      </div>
      <div className="sk sk-filters" />
      <div className="radar-table">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="sk sk-row" />
        ))}
      </div>
    </div>
  );
}
