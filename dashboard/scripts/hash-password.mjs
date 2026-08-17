// Generate a GUEST_PASSWORD_HASH for the credentials login.
// Usage: node scripts/hash-password.mjs 'your-chosen-password'
// Prints: pbkdf2:<iterations>:<saltB64>:<hashB64>  — store this as GUEST_PASSWORD_HASH.
// The plaintext password is never stored; only this hash goes into env.
const pw = process.argv[2];
if (!pw) {
  console.error("usage: node scripts/hash-password.mjs 'password'");
  process.exit(1);
}
const iterations = 210000;
const salt = crypto.getRandomValues(new Uint8Array(16));
const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveBits']);
const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', salt, iterations, hash: 'SHA-256' }, key, 256);
const b64 = (u8) => Buffer.from(u8).toString('base64');
console.log(`pbkdf2:${iterations}:${b64(salt)}:${b64(new Uint8Array(bits))}`);
