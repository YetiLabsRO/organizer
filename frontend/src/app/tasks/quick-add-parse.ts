import { PRIORITY_HIGH, PRIORITY_LOW } from './task-meta';

/**
 * Quick-add syntax parsing.
 *
 * Grammar (all optional, order-independent):
 *   #tag            — attach an existing tag. Unknown tags are LEFT IN THE TITLE verbatim.
 *   @project        — attach an existing project. Unknown projects are likewise left as text.
 *   !!              — trailing marker: high priority
 *   ??              — trailing marker: low priority
 *   (ddl: DATE)     — deadline. DATE is an ISO date or a natural phrase (see parseNaturalDate).
 *                     If DATE does not parse, the whole `(ddl: …)` is left in the title rather
 *                     than silently dropping what the user typed.
 *
 * Tag/project tokens are *not* stripped here — resolution is async, and only tokens that
 * actually resolve may be removed. Use `stripTokens` once you know which ones matched.
 */
export interface QuickAddParse {
  /** Title with the deadline block and priority marker removed; #tag/@project tokens still present. */
  text: string;
  /** Tag tokens as typed, de-duplicated case-insensitively. */
  tagSlugs: string[];
  projectSlug?: string;
  priority?: number;
  endDate?: Date;
}

const WEEKDAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];

const NUMBER_WORDS: { [word: string]: number } = {
  a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6,
  seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12,
};

export function parseQuickAdd(raw: string, now: Date = new Date()): QuickAddParse {
  let text = raw.trim();

  // (ddl: …) — only consume it when the date actually parses.
  let endDate: Date | undefined;
  const ddl = text.match(/\(\s*ddl\s*:\s*([^)]+?)\s*\)/i);
  if (ddl?.index !== undefined) {
    const parsed = parseNaturalDate(ddl[1], now);
    if (parsed) {
      endDate = parsed;
      text = `${text.slice(0, ddl.index)} ${text.slice(ddl.index + ddl[0].length)}`.trim();
    }
  }

  // Trailing !! / ?? priority marker (checked after the deadline block is removed, so
  // "walk the dog (ddl: friday) !!" works as well as "walk the dog !! (ddl: friday)").
  let priority: number | undefined;
  const high = text.match(/\s*!!+$/);
  const low = text.match(/\s*\?\?+$/);
  if (high?.index !== undefined) {
    priority = PRIORITY_HIGH;
    text = text.slice(0, high.index).trim();
  } else if (low?.index !== undefined) {
    priority = PRIORITY_LOW;
    text = text.slice(0, low.index).trim();
  }

  const seen = new Set<string>();
  const tagSlugs = [...text.matchAll(/(?:^|\s)#([\w-]+)/g)]
    .map((m) => m[1])
    .filter((slug) => {
      const key = slug.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

  const projectSlug = text.match(/(?:^|\s)@([\w-]+)/)?.[1];

  return { text: text.replace(/\s+/g, ' ').trim(), tagSlugs, projectSlug, priority, endDate };
}

/** Remove only the tokens that actually resolved, leaving unknown ones as literal text. */
export function stripTokens(text: string, tagSlugs: string[], projectSlug?: string): string {
  let out = text;
  for (const slug of tagSlugs) {
    out = out.replace(new RegExp(`(^|\\s)#${escapeRegExp(slug)}(?=\\s|$)`, 'gi'), '$1');
  }
  if (projectSlug) {
    out = out.replace(new RegExp(`(^|\\s)@${escapeRegExp(projectSlug)}(?=\\s|$)`, 'gi'), '$1');
  }
  return out.replace(/\s+/g, ' ').trim();
}

/**
 * Parse a deadline phrase. Returns null when nothing matches, so the caller can leave the
 * user's text untouched rather than guess at a date.
 *
 * Supported: `YYYY-MM-DD`, `today`, `tomorrow`, `next week|month|year`,
 * `[next|this] <weekday>`, and `[in] N <days|weeks|months|years> [from now]`
 * where N is a digit or a number word ("two weeks from now").
 *
 * Dates land at 23:59 local — a deadline of "today" should not be instantly overdue.
 */
export function parseNaturalDate(input: string, now: Date = new Date()): Date | null {
  const s = input.trim().toLowerCase().replace(/\s+/g, ' ');
  if (!s) return null;

  const iso = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (iso) {
    const [y, m, d] = [+iso[1], +iso[2], +iso[3]];
    const date = new Date(y, m - 1, d);
    // Reject impossible dates (JS would roll 2026-02-31 over into March).
    const valid = date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d;
    return valid ? endOfDay(date) : null;
  }

  if (s === 'today') return endOfDay(now);
  if (s === 'tomorrow') return endOfDay(addDays(now, 1));
  if (s === 'next week') return endOfDay(addDays(now, 7));
  if (s === 'next month') return endOfDay(addMonths(now, 1));
  if (s === 'next year') return endOfDay(addMonths(now, 12));

  const weekday = s.match(/^(?:(?:next|this)\s+)?(sunday|monday|tuesday|wednesday|thursday|friday|saturday)$/);
  if (weekday) return endOfDay(nextWeekday(now, WEEKDAYS.indexOf(weekday[1])));

  const relative = s.match(/^(?:in\s+)?(\d+|[a-z]+)\s+(day|days|week|weeks|month|months|year|years)(?:\s+from\s+now)?$/);
  if (relative) {
    const raw = relative[1];
    const n = /^\d+$/.test(raw) ? parseInt(raw, 10) : NUMBER_WORDS[raw];
    if (!n || n <= 0) return null;
    const unit = relative[2];
    if (unit.startsWith('day')) return endOfDay(addDays(now, n));
    if (unit.startsWith('week')) return endOfDay(addDays(now, n * 7));
    if (unit.startsWith('month')) return endOfDay(addMonths(now, n));
    if (unit.startsWith('year')) return endOfDay(addMonths(now, n * 12));
  }

  return null;
}

/** The next occurrence of `target`, always strictly in the future ("next friday" on a Friday = +7d). */
function nextWeekday(now: Date, target: number): Date {
  const date = new Date(now);
  const delta = (target - date.getDay() + 7) % 7;
  date.setDate(date.getDate() + (delta === 0 ? 7 : delta));
  return date;
}

function addDays(date: Date, n: number): Date {
  const out = new Date(date);
  out.setDate(out.getDate() + n);
  return out;
}

function addMonths(date: Date, n: number): Date {
  const out = new Date(date);
  out.setMonth(out.getMonth() + n);
  return out;
}

function endOfDay(date: Date): Date {
  const out = new Date(date);
  out.setHours(23, 59, 0, 0);
  return out;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
