import fs from 'node:fs';
import path from 'node:path';
import { isVerticalSlug, type VerticalSlug } from './verticals';

const CONTENT_ROOT = path.join(process.cwd(), '.content');

function verticalDir(vertical: VerticalSlug): string {
  if (!isVerticalSlug(vertical)) {
    // Should be unreachable: every caller narrows `vertical` via isVerticalSlug (or a
    // notFound()) before it gets here. Guard anyway so a bad value can never turn into
    // a path read outside .content/.
    throw new Error(`content: unknown vertical "${vertical}"`);
  }
  return path.join(CONTENT_ROOT, vertical);
}

export function getManifest(vertical: VerticalSlug): any | null {
  const p = path.join(verticalDir(vertical), 'manifest.json');
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

export function getReport(vertical: VerticalSlug, slug: string): any | null {
  if (!/^[\w.-]+$/.test(slug)) return null;
  const p = path.join(verticalDir(vertical), 'reports', slug + '.json');
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

export function siblingNav(manifest: any, slug: string) {
  const list = manifest.reports as any[];
  const me = list.find((r) => r.slug === slug);
  if (!me) return { prev: null, next: null, sameDay: [] };
  const sameKind = list.filter((r) => r.kind === me.kind);
  const i = sameKind.findIndex((r) => r.slug === slug);
  return {
    prev: i > 0 ? sameKind[i - 1] : null,
    next: i >= 0 && i < sameKind.length - 1 ? sameKind[i + 1] : null,
    sameDay: list.filter((r) => r.date === me.date && r.slug !== slug),
  };
}

export const KIND_LABEL: Record<string, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly retro',
};
