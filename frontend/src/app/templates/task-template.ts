import { Tag } from '../tags/tag';

export type Frequency = 'daily' | 'weekly' | 'monthly' | 'yearly';

export interface TaskTemplate {
  id?: number;
  title: string;
  description?: string | null;
  priority?: number;
  estimated_time?: number | null;
  project?: number; // matches Task.project so the shared project picker's [(projectId)] binds cleanly

  _tags: Tag[]; // hydrated chip objects; required so the shared tag-chips [(tags)] binds cleanly
  tags: number[]; // for writing references

  // Recurrence rule (structured; `rrule` reserved for a future iCal upgrade).
  frequency: Frequency;
  interval: number;
  day_of_month?: number | null;
  weekdays?: number[] | null; // 0 = Monday … 6 = Sunday
  month_of_year?: number | null;
  start_on?: string | null; // ISO date (YYYY-MM-DD)
  end_on?: string | null;
  rrule?: string | null;

  // Generation controls.
  lead_time_days?: number;
  skip_if_previous_open?: boolean;
  is_active?: boolean;

  // Read-only, server-computed.
  last_generated_occurrence?: string | null;
  schedule_summary?: string;
  next_occurrence?: string | null;
  created_date?: string;
  changed_date?: string;
}

export const WEEKDAY_LABELS: { value: number; label: string }[] = [
  { value: 0, label: 'Mon' },
  { value: 1, label: 'Tue' },
  { value: 2, label: 'Wed' },
  { value: 3, label: 'Thu' },
  { value: 4, label: 'Fri' },
  { value: 5, label: 'Sat' },
  { value: 6, label: 'Sun' },
];
