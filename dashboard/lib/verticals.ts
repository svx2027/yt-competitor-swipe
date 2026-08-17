// Single source of truth for every niche this dashboard serves. Every vertical-aware
// module (auth, middleware, content, share, routing) reads from this registry instead
// of hardcoding vertical slugs, so adding a new niche later is a one-file change here
// plus the actual content/pipeline data for that niche (owned by the pipeline agent,
// not this file).

export const VERTICAL_SLUGS = ['fitness', 'outdoors'] as const;

export type VerticalSlug = (typeof VERTICAL_SLUGS)[number];

export type VerticalStatus = 'live' | 'pending';

export type PendingCopy = {
  headline: string;
  body: string;
};

export type VerticalDef = {
  slug: VerticalSlug;
  /** Short display name, e.g. for nav and page titles. */
  name: string;
  /** Fuller descriptive label for prose contexts. */
  nicheLabel: string;
  accentLight: string;
  accentDark: string;
  /** Content-voice label ("Strategist take"), not a per-client brand string. Same for every vertical. */
  takeLabel: string;
  /** Path to this vertical's calendar source, relative to the repo root (one level above dashboard/). */
  calendarPath: string;
  /** Matches the .content/CONTENTDIR/ directory this vertical's ingested reports live under. */
  contentDir: string;
  status: VerticalStatus;
  /** Set only for status "pending": copy shown in place of report content. */
  pendingCopy?: PendingCopy;
};

export const VERTICALS: Record<VerticalSlug, VerticalDef> = {
  fitness: {
    slug: 'fitness',
    name: 'Fitness Gear',
    nicheLabel: 'Home fitness gear reviews',
    accentLight: '#6d5bb0',
    accentDark: '#b9abe8',
    takeLabel: 'Strategist take',
    calendarPath: '../calendar.yaml',
    contentDir: 'fitness',
    status: 'live',
  },
  outdoors: {
    slug: 'outdoors',
    name: 'Outdoor Gear',
    nicheLabel: 'Outdoor and camping gear reviews',
    // Forest green: distinct from fitness's violet and from every status color in
    // globals.css; contrast verified against both theme surfaces.
    // Keep in sync with the [data-vertical='outdoors'] block in app/globals.css.
    accentLight: '#1f6b4a',
    accentDark: '#8fd6b4',
    takeLabel: 'Strategist take',
    calendarPath: '../verticals/outdoors/calendar.yaml',
    contentDir: 'outdoors',
    status: 'pending',
    pendingCopy: {
      headline: 'Outdoor gear gets the same daily competitive read fitness gear relies on.',
      body: 'The scan, scoring, and verification pipeline are already built. Your first report appears here automatically once it clears verification, no setup required.',
    },
  },
};

export const VERTICAL_LIST: VerticalDef[] = VERTICAL_SLUGS.map((s) => VERTICALS[s]);

export function isVerticalSlug(value: string | null | undefined): value is VerticalSlug {
  return !!value && (VERTICAL_SLUGS as readonly string[]).includes(value);
}

/** Landing vertical for an admin session, which has no home vertical of its own. */
export const DEFAULT_VERTICAL: VerticalSlug = 'fitness';

/** True if a session may view this vertical's content: an admin may view any vertical,
 * a client session only its own. Shared by the vertical layout's notFound() gate and
 * every generateMetadata that would otherwise leak a vertical's identity through the
 * page title even when the page body itself is correctly blocked, so the two checks
 * can never drift out of sync with each other. */
export function canAccessVertical(
  session: { user?: { role?: string; vertical?: string } } | null | undefined,
  vertical: VerticalSlug,
): boolean {
  const role = session?.user?.role;
  const sessionVertical = session?.user?.vertical;
  return role === 'admin' || sessionVertical === vertical;
}
