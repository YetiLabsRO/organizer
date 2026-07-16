/** Shape of the `GET /api/task/stats/` payload (see tasks/api/stats.py). */

export interface TagCount {
  slug: string | null;
  name: string | null;
  color: string | null;
  count: number;
}

export interface PeriodCount {
  period: string;
  count: number;
}

export interface TagSeries {
  slug: string | null;
  name: string | null;
  color: string | null;
  counts: number[];
}

export interface SolvedByTagTimeline {
  periods: string[];
  series: TagSeries[];
}

export interface CreatedVsCompleted {
  period: string;
  created: number;
  completed: number;
}

export interface StatusCount {
  status: string;
  label: string;
  count: number;
}

export interface PriorityCount {
  priority: number;
  label: string;
  count: number;
}

export interface HeatmapDay {
  date: string;
  count: number;
}

export interface TagLeadTime {
  slug: string | null;
  name: string | null;
  color: string | null;
  avg_days: number | null;
  count: number;
}

/** Shape of the `GET /api/task/focus-counts/` payload (see `build_focus_counts` in
 *  tasks/api/stats.py). Counts span the whole filtered set, not the fetched window — the priority
 *  bands are mutually exclusive and sum to `total`, while `due_today` overlaps `overdue`. */
export interface TaskFocusCounts {
  total: number;
  overdue: number;
  high: number;
  normal: number;
  low: number;
  due_today: number;
}

export interface TaskStats {
  bucket: 'day' | 'week';
  totals: { total: number; completed: number; open: number };
  tag_distribution: TagCount[];
  solved_timeline: PeriodCount[];
  solved_by_tag_timeline: SolvedByTagTimeline;
  created_vs_completed_timeline: CreatedVsCompleted[];
  status_breakdown: StatusCount[];
  priority_breakdown: PriorityCount[];
  calendar_heatmap: HeatmapDay[];
  time_to_completion_by_tag: TagLeadTime[];
}
