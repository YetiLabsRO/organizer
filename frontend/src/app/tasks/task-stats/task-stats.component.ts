import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, ParamMap, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { Subject, of } from 'rxjs';
import { catchError, debounceTime, switchMap, tap } from 'rxjs/operators';
import { ChartConfiguration } from 'chart.js';

import { Tag } from '../../tags/tag';
import { TagService } from '../../tags/tag.service';
import { TagColorPipe } from '../../tags/tag-color.pipe';
import { TaskFilters } from '../task-filters';
import { TaskStats } from '../task-stats.model';
import { TaskStatsService } from '../task-stats.service';
import { ChartCanvasComponent } from '../../shared/chart-canvas/chart-canvas.component';
import { CalendarHeatmapComponent } from '../../shared/calendar-heatmap/calendar-heatmap.component';

type CompletedState = 'all' | 'todo' | 'done';
type PeriodKey = 'today' | 'week' | 'month' | 'all' | 'custom';

const UNTAGGED = '(untagged)';
const FALLBACK_COLOR = '#adb5bd';
const STATUS_COLORS: { [k: string]: string } = {
  idea: '#0dcaf0',
  blocked: '#dc3545',
  inprogress: '#0d6efd',
  givenup: '#6c757d',
};
const PRIORITY_COLORS: { [k: number]: string } = { 4: '#dc3545', 2: '#0d6efd', 1: '#adb5bd' };

@Component({
  selector: 'app-task-stats',
  standalone: true,
  imports: [FormsModule, RouterLink, TagColorPipe, ChartCanvasComponent, CalendarHeatmapComponent],
  templateUrl: './task-stats.component.html',
  styleUrls: ['./task-stats.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskStatsComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly statsService = inject(TaskStatsService);
  private readonly tagService = inject(TagService);

  readonly allTags = signal<Tag[]>([]);
  readonly stats = signal<TaskStats | null>(null);
  readonly loading = signal(true);
  readonly error = signal(false);

  private readonly params = toSignal(this.route.queryParamMap);

  // Current filter state, derived from the URL (the single source of truth).
  readonly bucket = computed<'day' | 'week'>(() => (this.params()?.get('bucket') === 'week' ? 'week' : 'day'));
  readonly completedState = computed<CompletedState>(() => {
    const c = this.params()?.get('completed');
    return c === 'true' ? 'done' : c === 'false' ? 'todo' : 'all';
  });
  readonly activeSlugs = computed(() => new Set(this.params()?.getAll('tags') ?? []));

  // Completion-date window ("period") state, derived from the URL.
  readonly afterParam = computed(() => this.params()?.get('completed_after') ?? null);
  readonly beforeParam = computed(() => this.params()?.get('completed_before') ?? null);
  readonly periodActive = computed(() => !!this.afterParam() || !!this.beforeParam());
  readonly activePeriod = computed<PeriodKey>(() => {
    const a = this.afterParam();
    const b = this.beforeParam();
    if (!a && !b) return 'all';
    const p = this.periodPresets();
    if (a === p.today.after && b === p.today.before) return 'today';
    if (a === p.week.after && b === p.week.before) return 'week';
    if (a === p.month.after && b === p.month.before) return 'month';
    return 'custom';
  });

  searchInput = '';
  private readonly search$ = new Subject<string>();

  constructor() {
    this.tagService.getTags().subscribe((tags) => this.allTags.set(tags));

    // Keep the search box in sync with the URL (e.g. on back/forward or a shared link).
    effect(() => {
      this.searchInput = this.params()?.get('contains') ?? '';
    });

    // One in-flight request; switchMap cancels superseded fetches as filters change.
    this.route.queryParamMap
      .pipe(
        tap(() => {
          this.loading.set(true);
          this.error.set(false);
        }),
        switchMap((params) =>
          this.statsService.getStats(this.filtersFromParams(params), this.bucketFromParams(params)).pipe(
            catchError(() => {
              this.error.set(true);
              return of(null);
            }),
          ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe((stats) => {
        if (stats) this.stats.set(stats);
        this.loading.set(false);
      });

    this.search$
      .pipe(debounceTime(250), takeUntilDestroyed())
      .subscribe((term) => this.updateParams({ contains: term.trim() || null }));
  }

  // --- filter-bar interactions (all write to the URL) ---

  setCompleted(state: CompletedState): void {
    const completed = state === 'all' ? null : state === 'done' ? 'true' : 'false';
    this.updateParams({ completed });
  }

  setBucket(bucket: 'day' | 'week'): void {
    this.updateParams({ bucket: bucket === 'day' ? null : 'week' });
  }

  onSearch(term: string): void {
    this.searchInput = term;
    this.search$.next(term);
  }

  setPeriod(key: 'today' | 'week' | 'month' | 'all'): void {
    if (key === 'all') {
      this.updateParams({ completed_after: null, completed_before: null });
      return;
    }
    const preset = this.periodPresets()[key];
    this.updateParams({ completed_after: preset.after, completed_before: preset.before });
  }

  onPeriodFrom(value: string): void {
    this.updateParams({ completed_after: value || null });
  }

  onPeriodTo(value: string): void {
    this.updateParams({ completed_before: value || null });
  }

  toggleTag(tag: Tag): void {
    const slugs = new Set(this.activeSlugs());
    if (slugs.has(tag.slug)) slugs.delete(tag.slug);
    else slugs.add(tag.slug);
    this.updateParams({ tags: slugs.size ? [...slugs] : null });
  }

  isTagActive(tag: Tag): boolean {
    return this.activeSlugs().has(tag.slug);
  }

  private updateParams(changes: { [k: string]: string | string[] | null }): void {
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: changes,
      queryParamsHandling: 'merge',
    });
  }

  private bucketFromParams(params: ParamMap): 'day' | 'week' {
    return params.get('bucket') === 'week' ? 'week' : 'day';
  }

  /** Rebuild a `TaskFilters` from URL params. Only slugs are needed for the query, so lightweight
   *  tag stand-ins are enough (no dependency on the loaded tag list for fetching). */
  private filtersFromParams(params: ParamMap): TaskFilters {
    const c = params.get('completed');
    const completed = c === null ? null : c === 'true';
    const slugs = params.getAll('tags');
    const tags = slugs.length ? slugs.map((slug) => ({ slug }) as Tag) : null;
    const forToday = params.get('for_today') === 'true' ? true : null;
    const todayView = params.get('today_view') === 'true' ? true : null;
    const filters = new TaskFilters(completed, params.get('contains'), null, tags, forToday, todayView);
    // Carried over from a project-scoped list, so its Stats link stays about that project.
    const project = Number(params.get('project'));
    filters.project = Number.isFinite(project) && project > 0 ? project : null;
    const after = params.get('completed_after');
    const before = params.get('completed_before');
    if (after) filters.completed_after = this.parseDate(after);
    if (before) filters.completed_before = this.parseDate(before);
    return filters;
  }

  /** Preset windows (as local ISO dates) relative to today, for the period selector. */
  private periodPresets(): { [K in 'today' | 'week' | 'month']: { after: string; before: string } } {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const minus = (n: number) => {
      const d = new Date(today);
      d.setDate(d.getDate() - n);
      return d;
    };
    const t = this.iso(today);
    return {
      today: { after: t, before: t },
      week: { after: this.iso(minus(6)), before: t }, // rolling last 7 days
      month: { after: this.iso(minus(29)), before: t }, // rolling last 30 days
    };
  }

  private iso(d: Date): string {
    const m = `${d.getMonth() + 1}`.padStart(2, '0');
    const day = `${d.getDate()}`.padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
  }

  private parseDate(iso: string): Date {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d);
  }

  // --- chart configurations (computed from the stats payload) ---

  readonly distributionConfig = computed<ChartConfiguration | null>(() => {
    const rows = this.stats()?.tag_distribution ?? [];
    if (!rows.length) return null;
    return {
      type: 'bar',
      data: {
        labels: rows.map((r) => r.name ?? UNTAGGED),
        datasets: [
          {
            label: 'Tasks',
            data: rows.map((r) => r.count),
            backgroundColor: rows.map((r) => r.color ?? FALLBACK_COLOR),
            borderColor: 'rgba(0,0,0,0.15)',
            borderWidth: 1,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    };
  });

  readonly solvedTimelineConfig = computed<ChartConfiguration | null>(() => {
    const s = this.stats();
    const rows = s?.solved_timeline ?? [];
    if (!rows.length) return null;
    return {
      type: 'bar',
      data: {
        labels: rows.map((r) => r.period),
        datasets: [
          { label: `Solved / ${s!.bucket}`, data: rows.map((r) => r.count), backgroundColor: '#5b8cff' },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    };
  });

  readonly stackedAreaConfig = computed<ChartConfiguration | null>(() => {
    const t = this.stats()?.solved_by_tag_timeline;
    if (!t || !t.periods.length) return null;
    return {
      type: 'line',
      data: {
        labels: t.periods,
        datasets: t.series.map((series) => {
          const color = series.color ?? FALLBACK_COLOR;
          let running = 0;
          return {
            label: series.name ?? UNTAGGED,
            data: series.counts.map((c) => (running += c)),
            borderColor: color,
            backgroundColor: this.rgba(color, 0.4),
            fill: true,
            tension: 0.25,
            pointRadius: 0,
          };
        }),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        scales: { y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } } },
      },
    };
  });

  readonly burnupConfig = computed<ChartConfiguration | null>(() => {
    const rows = this.stats()?.created_vs_completed_timeline ?? [];
    if (!rows.length) return null;
    let created = 0;
    let completed = 0;
    return {
      type: 'line',
      data: {
        labels: rows.map((r) => r.period),
        datasets: [
          {
            label: 'Created (cumulative)',
            data: rows.map((r) => (created += r.created)),
            borderColor: '#6c757d',
            backgroundColor: this.rgba('#6c757d', 0.1),
            fill: false,
            tension: 0.25,
            pointRadius: 0,
          },
          {
            label: 'Completed (cumulative)',
            data: rows.map((r) => (completed += r.completed)),
            borderColor: '#198754',
            backgroundColor: this.rgba('#198754', 0.2),
            fill: true,
            tension: 0.25,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    };
  });

  readonly statusConfig = computed<ChartConfiguration | null>(() =>
    this.doughnut(
      this.stats()?.status_breakdown.map((r) => ({ label: r.label, count: r.count, color: STATUS_COLORS[r.status] })),
    ),
  );

  readonly priorityConfig = computed<ChartConfiguration | null>(() =>
    this.doughnut(
      this.stats()?.priority_breakdown.map((r) => ({
        label: r.label,
        count: r.count,
        color: PRIORITY_COLORS[r.priority],
      })),
    ),
  );

  readonly leadTimeConfig = computed<ChartConfiguration | null>(() => {
    const rows = (this.stats()?.time_to_completion_by_tag ?? []).filter((r) => r.avg_days != null);
    if (!rows.length) return null;
    return {
      type: 'bar',
      data: {
        labels: rows.map((r) => r.name ?? UNTAGGED),
        datasets: [
          {
            label: 'Avg days to complete',
            data: rows.map((r) => r.avg_days as number),
            backgroundColor: rows.map((r) => r.color ?? FALLBACK_COLOR),
            borderColor: 'rgba(0,0,0,0.15)',
            borderWidth: 1,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true } },
      },
    };
  });

  private doughnut(rows?: { label: string; count: number; color?: string }[]): ChartConfiguration | null {
    if (!rows || !rows.length) return null;
    return {
      type: 'doughnut',
      data: {
        labels: rows.map((r) => r.label),
        datasets: [{ data: rows.map((r) => r.count), backgroundColor: rows.map((r) => r.color ?? FALLBACK_COLOR) }],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
    };
  }

  private rgba(hex: string, alpha: number): string {
    const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (!m) return `rgba(108,117,125,${alpha})`;
    const [r, g, b] = [m[1], m[2], m[3]].map((h) => parseInt(h, 16));
    return `rgba(${r},${g},${b},${alpha})`;
  }
}
