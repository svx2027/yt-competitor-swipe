import Link from 'next/link';
import { VERTICAL_LIST, type VerticalSlug } from '@/lib/verticals';

// Admin-only: the calling page gates this on session.user.role === 'admin'. Plain
// links, no client JS needed. Each option carries its own data-vertical attribute so
// its dot previews that vertical's true accent color regardless of which vertical's
// theme is currently active on the page (CSS custom properties re-resolve per
// element, see the [data-vertical] blocks in globals.css).
export default function VerticalSwitcher({ current }: { current: VerticalSlug }) {
  return (
    <nav className="v-switcher" aria-label="Switch vertical">
      {VERTICAL_LIST.map((v) => (
        <Link
          key={v.slug}
          href={`/${v.slug}`}
          data-vertical={v.slug}
          className={`v-switcher-item${v.slug === current ? ' on' : ''}`}
          aria-current={v.slug === current ? 'page' : undefined}
          title={v.nicheLabel}
        >
          <span className="v-switcher-dot" aria-hidden="true" />
          {v.name}
        </Link>
      ))}
    </nav>
  );
}
