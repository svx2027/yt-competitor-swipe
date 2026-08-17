import NextAuth, { type DefaultSession } from 'next-auth';
import Google from 'next-auth/providers/google';
import Credentials from 'next-auth/providers/credentials';
import { VERTICAL_LIST, type VerticalSlug } from '@/lib/verticals';

export type Role = 'client' | 'admin';
// '*' marks an admin session: authorized for every vertical, not just one.
export const ADMIN_VERTICAL = '*' as const;
export type SessionVertical = VerticalSlug | typeof ADMIN_VERTICAL;

declare module 'next-auth' {
  interface Session {
    user: {
      vertical?: SessionVertical;
      role?: Role;
    } & DefaultSession['user'];
  }
  interface User {
    vertical?: SessionVertical;
    role?: Role;
  }
}

// Augmenting "@auth/core/jwt" directly (not the "next-auth/jwt" re-export barrel):
// next-auth/jwt.d.ts is a bare `export * from "@auth/core/jwt"` with no local
// declarations of its own, which TypeScript rejects as an augmentation target
// (TS2664, "Invalid module name in augmentation"). @auth/core/jwt is where the JWT
// interface actually lives, and it is what the jwt() callback's `token` param resolves
// to under the hood, so this is what next-auth's own docs recommend augmenting.
declare module '@auth/core/jwt' {
  interface JWT {
    vertical?: SessionVertical;
    role?: Role;
  }
}

function isAllowed(email?: string | null) {
  if (!email) return false;
  const list = (process.env.ALLOWED_EMAILS || '')
    .toLowerCase()
    .split(/[,\s]+/)
    .filter(Boolean);
  return list.includes(email.toLowerCase());
}

// Edge-safe password verify (Web Crypto PBKDF2). Stored form: pbkdf2:<iter>:<saltB64>:<hashB64>
// Delimiter is ':' (not '$') because dotenv/@next/env expand '$' in .env values.
function b64ToBytes(s: string): Uint8Array {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function verifyPassword(input: string, stored?: string | null) {
  if (!stored) return false;
  const parts = stored.split(':');
  if (parts.length !== 4 || parts[0] !== 'pbkdf2') return false;
  const iterations = parseInt(parts[1], 10);
  let salt: Uint8Array, expected: Uint8Array;
  try {
    salt = b64ToBytes(parts[2]);
    expected = b64ToBytes(parts[3]);
  } catch {
    return false;
  }
  const material = new Uint8Array(new TextEncoder().encode(input));
  const key = await crypto.subtle.importKey('raw', material as BufferSource, 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt: salt as BufferSource, iterations, hash: 'SHA-256' },
    key,
    expected.length * 8,
  );
  const actual = new Uint8Array(bits);
  if (actual.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < actual.length; i++) diff |= actual[i] ^ expected[i];
  return diff === 0;
}

// One credential slot per vertical (CLIENT_<VERTICAL>_USERNAME / _PASSWORD_HASH), plus
// the legacy single-tenant guest account kept alive during the multi-vertical transition.
type CredentialCandidate = {
  id: string;
  label: string;
  username: string;
  hash: string;
  vertical: VerticalSlug;
};

function credentialCandidates(): CredentialCandidate[] {
  const list: CredentialCandidate[] = [];
  for (const v of VERTICAL_LIST) {
    const username = process.env[`CLIENT_${v.slug.toUpperCase()}_USERNAME`];
    const hash = process.env[`CLIENT_${v.slug.toUpperCase()}_PASSWORD_HASH`];
    if (username && hash) {
      list.push({ id: `client-${v.slug}`, label: username, username, hash, vertical: v.slug });
    }
  }
  // The legacy guest login predates the multi-vertical migration and is mapped to the
  // vertical that existed before it, so an existing guest link keeps working while
  // clients migrate to CLIENT_FITNESS_*.
  // TODO(remove after transition): retire once every guest is on CLIENT_FITNESS_USERNAME.
  const guestUser = process.env.GUEST_USERNAME;
  const guestHash = process.env.GUEST_PASSWORD_HASH;
  if (guestUser && guestHash) {
    list.push({
      id: 'guest',
      label: process.env.GUEST_LABEL || guestUser,
      username: guestUser,
      hash: guestHash,
      vertical: 'fitness',
    });
  }
  return list;
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  providers: [
    Google,
    Credentials({
      name: 'Client login',
      credentials: { username: {}, password: {} },
      async authorize(creds) {
        if (typeof creds?.username !== 'string' || typeof creds?.password !== 'string') return null;
        const candidate = credentialCandidates().find((c) => c.username === creds.username);
        if (!candidate) return null;
        const ok = await verifyPassword(creds.password, candidate.hash);
        if (!ok) return null;
        return { id: candidate.id, name: candidate.label, vertical: candidate.vertical, role: 'client' };
      },
    }),
  ],
  session: { strategy: 'jwt', maxAge: 30 * 24 * 3600 },
  pages: { signIn: '/login', error: '/login' },
  callbacks: {
    signIn({ account, profile }) {
      if (account?.provider === 'credentials') return true; // authorize() already validated
      return isAllowed(profile?.email) && profile?.email_verified !== false;
    },
    jwt({ token, user, account }) {
      if (user) {
        if (account?.provider === 'google') {
          // signIn() above already enforced ALLOWED_EMAILS, so a Google session is always admin.
          token.role = 'admin';
          token.vertical = ADMIN_VERTICAL;
        } else {
          token.vertical = user.vertical;
          token.role = user.role;
        }
      } else if (!token.role || !token.vertical) {
        // Backfill for a session cookie issued before this migration (no vertical/role
        // claim baked in). A Google sign-in always carries an email; the old guest
        // credentials flow never did, and was always the pre-migration vertical. This
        // only fires once per stale session; the backfilled claim then persists on the token.
        if (token.email) {
          token.role = 'admin';
          token.vertical = ADMIN_VERTICAL;
        } else {
          token.role = 'client';
          token.vertical = 'fitness';
        }
      }
      return token;
    },
    session({ session, token }) {
      if (session.user) {
        session.user.vertical = token.vertical;
        session.user.role = token.role;
      }
      return session;
    },
    authorized({ auth }) {
      return !!auth?.user;
    },
  },
});
