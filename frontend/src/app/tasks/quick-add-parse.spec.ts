import { parseQuickAdd, parseNaturalDate, stripTokens } from './quick-add-parse';
import { PRIORITY_HIGH, PRIORITY_LOW } from './task-meta';

// A fixed "now" so relative dates are deterministic: Monday 2026-07-13, 10:00 local.
const NOW = new Date(2026, 6, 13, 10, 0, 0);

const ymd = (d: Date | undefined | null) =>
  d ? `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` : null;

describe('parseNaturalDate', () => {
  it('parses ISO dates', () => {
    expect(ymd(parseNaturalDate('2026-07-20', NOW))).toBe('2026-07-20');
  });

  it('rejects impossible ISO dates instead of rolling them over', () => {
    expect(parseNaturalDate('2026-02-31', NOW)).toBeNull();
  });

  it('parses today and tomorrow', () => {
    expect(ymd(parseNaturalDate('today', NOW))).toBe('2026-07-13');
    expect(ymd(parseNaturalDate('tomorrow', NOW))).toBe('2026-07-14');
  });

  it('parses "next week" / "next month"', () => {
    expect(ymd(parseNaturalDate('next week', NOW))).toBe('2026-07-20');
    expect(ymd(parseNaturalDate('next month', NOW))).toBe('2026-08-13');
  });

  it('parses "next <weekday>"', () => {
    // NOW is a Monday; Wednesday is 2 days out.
    expect(ymd(parseNaturalDate('next wednesday', NOW))).toBe('2026-07-15');
    expect(ymd(parseNaturalDate('friday', NOW))).toBe('2026-07-17');
  });

  it('pushes a weekday that is today to the following week', () => {
    expect(ymd(parseNaturalDate('next monday', NOW))).toBe('2026-07-20');
  });

  it('parses "N units from now", with digits or number words', () => {
    expect(ymd(parseNaturalDate('two weeks from now', NOW))).toBe('2026-07-27');
    expect(ymd(parseNaturalDate('3 days', NOW))).toBe('2026-07-16');
    expect(ymd(parseNaturalDate('in 2 months', NOW))).toBe('2026-09-13');
  });

  it('lands at end of day so a deadline of today is not instantly overdue', () => {
    const d = parseNaturalDate('today', NOW)!;
    expect(d.getHours()).toBe(23);
    expect(d.getMinutes()).toBe(59);
  });

  it('returns null for unparseable input', () => {
    expect(parseNaturalDate('whenever', NOW)).toBeNull();
    expect(parseNaturalDate('', NOW)).toBeNull();
  });
});

describe('parseQuickAdd', () => {
  it('extracts a trailing !! as high priority', () => {
    const p = parseQuickAdd('Ship the release !!', NOW);
    expect(p.priority).toBe(PRIORITY_HIGH);
    expect(p.text).toBe('Ship the release');
  });

  it('extracts a trailing ?? as low priority', () => {
    const p = parseQuickAdd('Maybe refactor this ??', NOW);
    expect(p.priority).toBe(PRIORITY_LOW);
    expect(p.text).toBe('Maybe refactor this');
  });

  it('leaves priority unset when there is no marker', () => {
    expect(parseQuickAdd('Plain task', NOW).priority).toBeUndefined();
  });

  it('extracts (ddl: …) and removes it from the title', () => {
    const p = parseQuickAdd('Pay rent (ddl: 2026-08-01)', NOW);
    expect(ymd(p.endDate)).toBe('2026-08-01');
    expect(p.text).toBe('Pay rent');
  });

  it('accepts a natural-language deadline', () => {
    const p = parseQuickAdd('Call the bank (ddl: next wednesday)', NOW);
    expect(ymd(p.endDate)).toBe('2026-07-15');
    expect(p.text).toBe('Call the bank');
  });

  it('keeps an unparseable (ddl: …) as literal text rather than dropping it', () => {
    const p = parseQuickAdd('Do it (ddl: someday)', NOW);
    expect(p.endDate).toBeUndefined();
    expect(p.text).toBe('Do it (ddl: someday)');
  });

  it('handles a deadline and a priority marker together, in either order', () => {
    const a = parseQuickAdd('Fix bug (ddl: tomorrow) !!', NOW);
    expect(a.priority).toBe(PRIORITY_HIGH);
    expect(ymd(a.endDate)).toBe('2026-07-14');
    expect(a.text).toBe('Fix bug');

    const b = parseQuickAdd('Fix bug !! (ddl: tomorrow)', NOW);
    expect(b.priority).toBe(PRIORITY_HIGH);
    expect(ymd(b.endDate)).toBe('2026-07-14');
    expect(b.text).toBe('Fix bug');
  });

  it('collects tag and project tokens but leaves them in the text for later resolution', () => {
    const p = parseQuickAdd('Write docs #api #api @organizer', NOW);
    expect(p.tagSlugs).toEqual(['api']); // de-duplicated
    expect(p.projectSlug).toBe('organizer');
    expect(p.text).toBe('Write docs #api #api @organizer');
  });
});

describe('stripTokens', () => {
  it('removes only the tokens that resolved, keeping unknown ones as text', () => {
    const title = stripTokens('Write docs #api #nope @organizer', ['api'], 'organizer');
    expect(title).toBe('Write docs #nope');
  });

  it('is case-insensitive about the typed token', () => {
    expect(stripTokens('Review #API', ['API'])).toBe('Review');
  });

  it('leaves everything when nothing resolved', () => {
    expect(stripTokens('Ping #unknown', [])).toBe('Ping #unknown');
  });
});
