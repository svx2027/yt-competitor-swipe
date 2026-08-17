import fs from 'node:fs';
import path from 'node:path';
import { VERTICALS, type VerticalSlug } from '@/lib/verticals';

type CalendarPhase = { key: string; label: string; start: string; end: string };
type ParsedCalendar = { keyDate: string | null; phases: CalendarPhase[] };

function stripQuotesAndComment(raw: string): string {
  const v = raw.trim();
  if (v[0] === '"' || v[0] === "'") {
    const end = v.indexOf(v[0], 1);
    if (end > 0) return v.slice(1, end);
  }
  const hashIdx = v.indexOf('#');
  return (hashIdx >= 0 ? v.slice(0, hashIdx) : v).trim();
}

// Deliberately narrow parser for this repo's own hand-authored calendar YAML shape,
// not a general-purpose YAML parser: no multiline strings, flow style, or anchors.
// Reads only the two blocks the countdown needs, `verified.key_date` and
// `phases[].{key,label,start,end}` (boost_hooks lists are walked over and ignored).
// Never throws: any shape surprise just yields fewer fields, and the component below
// already treats a missing key_date as "render nothing".
function parseCalendarYaml(text: string): ParsedCalendar {
  const lines = text.split('\n');
  let keyDate: string | null = null;
  const phases: CalendarPhase[] = [];

  for (let i = 0; i < lines.length; i++) {
    if (keyDate === null && /^verified:\s*$/.test(lines[i])) {
      for (let j = i + 1; j < lines.length; j++) {
        if (/^\S/.test(lines[j])) break; // dedent back to a top-level key
        const m = lines[j].match(/^\s*key_date:\s*(.+)$/);
        if (m) {
          keyDate = stripQuotesAndComment(m[1]);
          break;
        }
      }
    }

    if (/^phases:\s*$/.test(lines[i])) {
      let cur: Partial<CalendarPhase> | null = null;
      for (let j = i + 1; j < lines.length; j++) {
        const line = lines[j];
        if (/^\S/.test(line)) break; // back to top level, phases block is over
        const start = line.match(/^ {2}- key:\s*(.+)$/);
        if (start) {
          if (cur?.key) phases.push(cur as CalendarPhase);
          cur = { key: stripQuotesAndComment(start[1]) };
          continue;
        }
        if (!cur) continue;
        const field = line.match(/^ {4}(label|start|end):\s*(.+)$/);
        if (field) (cur as Record<string, string>)[field[1]] = stripQuotesAndComment(field[2]);
      }
      if (cur?.key) phases.push(cur as CalendarPhase);
    }
  }
  return { keyDate, phases };
}

function readCalendar(calendarPath: string): ParsedCalendar | null {
  try {
    // calendarPath is authored relative to dashboard/ (e.g. "../calendar.yaml"),
    // which is process.cwd() for both `next dev` and the deployed server. See the
    // field comment on VerticalDef.calendarPath in lib/verticals.ts.
    const abs = path.resolve(process.cwd(), calendarPath);
    if (!fs.existsSync(abs)) return null;
    const parsed = parseCalendarYaml(fs.readFileSync(abs, 'utf8'));
    return parsed.keyDate ? parsed : null;
  } catch {
    return null;
  }
}

// en-CA formats as YYYY-MM-DD, giving a clean date-only key in the calendar's own
// timezone (Asia/Kolkata, fixed UTC+5:30, same convention the pipeline uses)
// regardless of the server's local time (Vercel runs UTC).
function todayIST(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
}

function daysBetween(fromISO: string, toISO: string): number {
  const [fy, fm, fd] = fromISO.split('-').map(Number);
  const [ty, tm, td] = toISO.split('-').map(Number);
  const from = Date.UTC(fy, fm - 1, fd);
  const to = Date.UTC(ty, tm - 1, td);
  return Math.round((to - from) / 86400000);
}

function currentPhaseLabel(phases: CalendarPhase[], todayISO: string): string | null {
  return phases.find((p) => p.start <= todayISO && todayISO <= p.end)?.label ?? null;
}

const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// The chip shows the literal date rather than deriving a "cycle year" label: different
// niches may name a cycle differently, and showing the wrong year to a client is worse
// than showing no year. Stating the date itself is unambiguous and correct for every
// vertical without per-vertical special-casing.
function formatDateHuman(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return `${d} ${MONTHS_SHORT[m - 1]} ${y}`;
}

export default function KeyDateCountdown({ vertical }: { vertical: VerticalSlug }) {
  const entry = VERTICALS[vertical];
  const calendar = readCalendar(entry.calendarPath);
  if (!calendar?.keyDate) return null;

  const today = todayIST();
  const days = daysBetween(today, calendar.keyDate);
  if (days < 0) return null; // key date has passed; a countdown reads as stale, not premium

  const phaseLabel = currentPhaseLabel(calendar.phases, today);
  const daysText = days === 0 ? 'Key date' : days === 1 ? '1 day out' : `${days} days out`;
  const title = `Key date: ${formatDateHuman(calendar.keyDate)}.${phaseLabel ? ` Currently in: ${phaseLabel}.` : ''}`;

  return (
    <span className="countdown-chip" title={title}>
      <span className="countdown-exam">{entry.name}</span>
      <span className="countdown-sep" aria-hidden="true">
        ·
      </span>
      <span className="countdown-days">{daysText}</span>
    </span>
  );
}
