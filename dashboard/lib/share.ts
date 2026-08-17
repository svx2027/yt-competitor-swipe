import { SignJWT, jwtVerify } from 'jose';
import { isVerticalSlug, type VerticalSlug } from './verticals';

function secret() {
  const s = process.env.SHARE_SECRET;
  if (!s) throw new Error('SHARE_SECRET is not set');
  return new TextEncoder().encode(s);
}

export async function createShareToken(slug: string, vertical: VerticalSlug, days: number) {
  return new SignJWT({ slug, vertical })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime(`${days}d`)
    .sign(secret());
}

export type ShareTokenPayload = { slug: string; vertical: VerticalSlug; exp?: number };

// Legacy compatibility: share tokens minted before the multi-vertical migration carry
// no `vertical` claim. Treat those as the vertical that existed pre-migration until
// 2026-08-31, then reject them outright so a stale, unrevoked link can't silently
// keep working forever. Move this cutover date out, or drop the fallback entirely,
// once no legacy links are known to still be circulating.
const LEGACY_TOKEN_CUTOFF = new Date('2026-08-31T23:59:59Z').getTime();

export async function verifyShareToken(token: string): Promise<ShareTokenPayload | null> {
  try {
    const { payload } = await jwtVerify(token, secret());
    if (typeof payload.slug !== 'string') return null;
    if (payload.vertical === undefined) {
      if (Date.now() > LEGACY_TOKEN_CUTOFF) return null;
      // Server-side only, never shown to the link recipient. Lets us monitor how much
      // legacy-token traffic is still alive before the 2026-08-31 cutover.
      console.warn(
        `share: accepted legacy pre-vertical share token for slug "${payload.slug}" (defaulting to vertical fitness); this fallback expires 2026-08-31`,
      );
      return { slug: payload.slug, vertical: 'fitness', exp: payload.exp };
    }
    if (typeof payload.vertical === 'string' && isVerticalSlug(payload.vertical)) {
      return { slug: payload.slug, vertical: payload.vertical, exp: payload.exp };
    }
    return null;
  } catch {
    return null;
  }
}
