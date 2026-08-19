import fs from 'node:fs';
import path from 'node:path';
import { isVerticalSlug, type VerticalSlug } from './verticals';

// Reads the Competitor Radar data that ingest.mjs copied into
// .content/<vertical>/competitors/ (registry.json + <slug>/windows/<window>.json).
// Same server-only, fs-read model as lib/content.ts: nothing here is ever fetched
// by the client, so competitor intel cannot be read without an authenticated page.

const CONTENT_ROOT = path.join(process.cwd(), '.content');
const SAFE = /^[\w.-]+$/; // slug / window are path segments; reject anything else

export type RadarFormat = 'long' | 'short' | 'live';
export type RadarSubject = 'Strength' | 'Cardio' | 'Recovery' | 'General';

export type RadarRow = {
  id: string;
  fmt: RadarFormat;
  subject: RadarSubject;
  theme: string;
  month: string; // YYYY-MM
  date: string; // YYYY-MM-DD
  views: number | null; // null = UNKNOWN, never 0
  likes: number | null;
  comments: number | null;
  vpd: number | null;
  mult: number | null;
  m26: string | null; // mapped 2026 publish date
  premiere: boolean;
  title: string;
  url: string;
};

export type WindowData = {
  schema_version: number;
  vertical: string;
  competitor: string;
  competitor_name: string;
  window: { from: string; to: string; label: string };
  generated_at: string;
  source: string;
  medians: Record<RadarFormat, number>;
  counts: { total: number; by_format: Record<RadarFormat, number> };
  rows: RadarRow[];
};

export type CompetitorEntry = {
  slug: string;
  name: string;
  handle: string;
  channel_id: string;
  subs: number;
  status: string;
  windows: string[];
  hasInsights?: boolean;
};

export type CompetitorRegistry = {
  schema_version: number;
  vertical: string;
  competitors: CompetitorEntry[];
};

function radarDir(vertical: VerticalSlug): string {
  if (!isVerticalSlug(vertical)) throw new Error(`competitors: unknown vertical "${vertical}"`);
  return path.join(CONTENT_ROOT, vertical, 'competitors');
}

export function getCompetitorRegistry(vertical: VerticalSlug): CompetitorRegistry | null {
  const p = path.join(radarDir(vertical), 'registry.json');
  if (!fs.existsSync(p)) return null;
  try {
    const reg = JSON.parse(fs.readFileSync(p, 'utf8')) as CompetitorRegistry;
    // Only surface competitors that actually have at least one window on disk.
    reg.competitors = (reg.competitors || []).filter((c) => SAFE.test(c.slug) && (c.windows || []).length > 0);
    return reg.competitors.length > 0 ? reg : null;
  } catch {
    return null;
  }
}

export function hasCompetitorRadar(vertical: VerticalSlug): boolean {
  return getCompetitorRegistry(vertical) !== null;
}

export function getCompetitorWindow(vertical: VerticalSlug, slug: string, window: string): WindowData | null {
  if (!SAFE.test(slug) || !SAFE.test(window)) return null;
  const p = path.join(radarDir(vertical), slug, 'windows', window + '.json');
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8')) as WindowData;
  } catch {
    return null;
  }
}

/** The window to show by default: the most recent by its `to` date. */
export function latestWindowKey(entry: CompetitorEntry): string | null {
  if (!entry.windows || entry.windows.length === 0) return null;
  // window keys are `<from>_<to>`; sort by the `to` half, lexical works on ISO dates
  return [...entry.windows].sort((a, b) => (a.split('_')[1] || '').localeCompare(b.split('_')[1] || '')).pop() || null;
}

/** Cycle year of a window key ("2024-08-01_2024-12-31" -> 2024). */
export function yearOfWindow(key: string): number {
  return parseInt(key.slice(0, 4), 10);
}

/** Windows oldest-first with their cycle year, for the year switcher. */
export function windowsWithYears(entry: CompetitorEntry): { key: string; year: number }[] {
  return [...(entry.windows || [])]
    .map((key) => ({ key, year: yearOfWindow(key) }))
    .sort((a, b) => a.year - b.year);
}

/** Combined view across every window: rows tagged with their cycle year, plus each
 *  year's medians. Used only for the "Both years" mode; single-year uses WindowData. */
export type CombinedRow = RadarRow & { year: number };
export type CombinedData = {
  years: number[];
  medians: Record<number, Record<RadarFormat, number>>;
  labels: Record<number, string>;
  rows: CombinedRow[];
  total: number;
};

export function getCombined(vertical: VerticalSlug, entry: CompetitorEntry): CombinedData | null {
  const parts: { year: number; data: WindowData }[] = [];
  for (const { key, year } of windowsWithYears(entry)) {
    const data = getCompetitorWindow(vertical, entry.slug, key);
    if (data) parts.push({ year, data });
  }
  if (parts.length === 0) return null;
  const medians: Record<number, Record<RadarFormat, number>> = {};
  const labels: Record<number, string> = {};
  const rows: CombinedRow[] = [];
  for (const { year, data } of parts) {
    medians[year] = data.medians;
    labels[year] = data.window.label;
    for (const r of data.rows) rows.push({ ...r, year });
  }
  // default combined ordering is by outlier multiple (age-fair across years)
  rows.sort((a, b) => (b.mult ?? 0) - (a.mult ?? 0));
  return { years: parts.map((p) => p.year), medians, labels, rows, total: rows.length };
}

// ---- month-wise insights (generated by the research repo's export_insights.py) ----
export type InsightRef = {
  year: number;
  id: string;
  title: string;
  url: string;
  views: number | null;
  mult: number | null;
  date: string;
  subject: string;
  theme: string;
  fmt: RadarFormat;
  m26: string | null;
};
export type FocusItem = {
  headline: string;
  fmt: RadarFormat;
  subject: string;
  kind: 'repeated' | 'rising' | 'faded';
  why: string;
  refs: InsightRef[];
  target_2026: string | null;
};
export type RepeatedWinner = { theme: string; fmt: RadarFormat; strength: number; refs: InsightRef[] };
export type MonthInsight = {
  month: string;
  label: string;
  counts: Record<string, number>;
  focus: FocusItem[];
  repeated: RepeatedWinner[];
  by_format: Record<string, Record<RadarFormat, InsightRef[]>>;
  subject_mix: Record<string, Record<string, number>>;
};
export type InsightsData = {
  schema_version: number;
  vertical: string;
  competitor: string;
  competitor_name: string;
  generated_at: string;
  years: number[];
  windows: Record<string, { from: string; to: string; label: string }>;
  medians: Record<string, Record<RadarFormat, number>>;
  months: Record<string, MonthInsight>;
};

export function getInsights(vertical: VerticalSlug, slug: string): InsightsData | null {
  if (!SAFE.test(slug)) return null;
  const p = path.join(radarDir(vertical), slug, 'insights.json');
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8')) as InsightsData;
  } catch {
    return null;
  }
}
