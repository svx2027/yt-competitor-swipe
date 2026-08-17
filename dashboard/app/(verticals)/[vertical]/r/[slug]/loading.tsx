// See app/(verticals)/[vertical]/loading.tsx for the general approach: real
// structural classes plus a `.skeleton` shimmer layer, sized to match this route's
// actual content so nothing shifts once it loads.
export default function Loading() {
  return (
    <div className="wrap">
      <header className="topbar">
        <div className="topbar-left">
          <div className="skeleton skeleton-line tall skeleton-w30" />
        </div>
        <div className="topbar-right">
          <div className="skeleton skeleton-avatar" />
        </div>
      </header>

      <nav className="repnav">
        <span className="skeleton skeleton-line skeleton-w30" />
        <span className="skeleton skeleton-line skeleton-w50" />
        <span className="skeleton skeleton-line skeleton-w30" />
      </nav>

      <div className="report">
        <div className="chips">
          <span className="skeleton skeleton-line skeleton-w30" />
        </div>
        <div className="skeleton skeleton-line tall skeleton-w70" />
        <div className="tabs">
          <div className="skeleton skeleton-line skeleton-w30" />
        </div>
        <div className="picks">
          {[0, 1, 2].map((i) => (
            <article className="pick" key={i}>
              <div className="pick-thumb skeleton" />
              <div className="pick-body">
                <div className="skeleton skeleton-line skeleton-w30" />
                <div className="skeleton skeleton-line tall skeleton-w70" />
                <div className="skeleton skeleton-line skeleton-w50" />
              </div>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}
