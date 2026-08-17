/** @type {import('next').NextConfig} */
const nextConfig = {
  // .content/ moved from a flat `.content/manifest.json` + `.content/reports/*.json`
  // layout to a per-vertical `.content/<vertical>/manifest.json` +
  // `.content/<vertical>/reports/*.json` layout. Verified (via Next's own bundled
  // next/dist/compiled/picomatch, matched directly against sample paths at both
  // depths) that `**` in this glob is depth-agnostic, so `./.content/**/*` already
  // covers the added nesting level with no pattern change required.
  outputFileTracingIncludes: {
    '/share/[token]': ['./.content/**/*'],
    '/api/share': ['./.content/**/*'],
    // KeyDateCountdown (components/KeyDateCountdown.tsx) reads each vertical's calendar
    // YAML straight off disk at request time via VerticalDef.calendarPath, which
    // lives outside dashboard/ (one level up, at the repo root). Without an explicit
    // include, Vercel's file tracer has no static import to follow and would omit
    // these from the serverless bundle, so the countdown would silently render
    // nothing in production even with a real calendar.yaml on disk. The glob is
    // deliberately loose: not every vertical has a calendar.yaml yet, and an
    // unmatched glob is a no-op, not a build error.
    '/[vertical]': ['../calendar.yaml', '../verticals/**/calendar.yaml'],
    '/[vertical]/r/[slug]': ['../calendar.yaml', '../verticals/**/calendar.yaml'],
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Robots-Tag', value: 'noindex, nofollow, noarchive' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
        ],
      },
    ];
  },
};

export default nextConfig;
