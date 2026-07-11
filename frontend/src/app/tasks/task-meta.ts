import { Task } from './task';

/** Canonical status list (value + label + Bootstrap badge class), shared by list and detail. */
export const TASK_STATUSES: { value: string; label: string; badgeClass: string }[] = [
  { value: 'idea', label: 'Idea', badgeClass: 'text-bg-light border' },
  { value: 'blocked', label: 'Blocked', badgeClass: 'text-bg-danger' },
  { value: 'inprogress', label: 'In progress', badgeClass: 'text-bg-info' },
  { value: 'givenup', label: 'Given up', badgeClass: 'text-bg-secondary' },
];

/** Canonical priority list (matches the backend integer choices), shared by list and detail. */
export const TASK_PRIORITIES: { value: number; label: string }[] = [
  { value: 4, label: 'High' },
  { value: 2, label: 'Normal' },
  { value: 1, label: 'Low' },
];

export const PRIORITY_HIGH = 4;
export const PRIORITY_NORMAL = 2;
export const PRIORITY_LOW = 1;

export function statusMeta(status?: string): { label: string; badgeClass: string } | null {
  return TASK_STATUSES.find((s) => s.value === status) ?? null;
}

/** Status to surface as a badge in the list — the default "Idea" is left unmarked to keep it quiet. */
export function listStatusMeta(status?: string): { label: string; badgeClass: string } | null {
  if (!status || status === 'idea') return null;
  return statusMeta(status);
}

export function priorityLabel(priority?: number): string {
  return TASK_PRIORITIES.find((p) => p.value === priority)?.label ?? '';
}

export type PriorityFlag = { icon: string; label: string; cls: string } | null;

/** High/low priority get a flag + colour; neutral priority is intentionally unmarked. */
export function priorityFlag(priority?: number): PriorityFlag {
  if (priority === PRIORITY_HIGH) return { icon: 'flag-fill', label: 'High priority', cls: 'text-danger' };
  if (priority === PRIORITY_LOW) return { icon: 'flag', label: 'Low priority', cls: 'text-secondary' };
  return null;
}

/** Row accent class keyed off priority (a coloured left border); neutral rows get no accent. */
export function priorityRowClass(priority?: number): string {
  if (priority === PRIORITY_HIGH) return 'priority-high';
  if (priority === PRIORITY_LOW) return 'priority-low';
  return '';
}

export type DeadlineInfo = { date: Date; state: 'overdue' | 'soon' | 'upcoming'; cls: string } | null;

const SOON_MS = 3 * 24 * 60 * 60 * 1000; // within 3 days counts as "due soon"

/** Classify a task's deadline for list emphasis. Completed / undated tasks return null. */
export function deadlineInfo(task: Task, now: Date = new Date()): DeadlineInfo {
  if (task.completed || !task.end_date) return null;
  const date = new Date(task.end_date);
  if (isNaN(date.getTime())) return null;
  const delta = date.getTime() - now.getTime();
  if (delta < 0) return { date, state: 'overdue', cls: 'text-danger fw-semibold' };
  if (delta < SOON_MS) return { date, state: 'soon', cls: 'text-warning-emphasis' };
  return { date, state: 'upcoming', cls: 'text-muted' };
}
