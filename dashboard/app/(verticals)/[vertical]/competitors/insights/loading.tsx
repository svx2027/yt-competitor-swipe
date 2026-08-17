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
      <div className="sk sk-filters" />
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="sk sk-row" style={{ height: 90, marginBottom: 10 }} />
      ))}
    </div>
  );
}
