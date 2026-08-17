// Next.js route-segment loading UI: shown automatically while this page's async
// server work (reading the manifest + latest report off disk) resolves during
// client-side navigation. Built from the same structural classes the real page
// uses (.pick, .pick-thumb, .cal-months, ...) so nothing shifts when real content
// swaps in, with `.skeleton` layered on top for the shimmer treatment.
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

      <section className="panel">
        <div className="skeleton skeleton-line tall skeleton-w30" />
        <div className="cal-months">
          <div className="skeleton skeleton-block" />
          <div className="skeleton skeleton-block" />
        </div>
      </section>

      <section className="latest">
        <div className="section-head">
          <div className="skeleton skeleton-line tall skeleton-w50" />
        </div>
        <div className="report">
          <div className="skeleton skeleton-line tall skeleton-w50" />
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
      </section>
    </div>
  );
}
