import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { formatDate } from '@angular/common';
import { RouterLink } from '@angular/router';

import { TaskService } from '../task.service';
import { Task } from '../task';
import { TagService } from '../../tags/tag.service';
import { Tag } from '../../tags/tag';
import { TagColorPipe } from '../../tags/tag-color.pipe';
import { ProjectService } from '../../projects/project.service';
import { TaskFilters } from '../task-filters';
import { Subject } from 'rxjs';
import { debounceTime } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TaskDrawerService } from '../task-drawer.service';
import { TaskEventsService, TaskEvent } from '../task-events.service';
import { TaskStatsService } from '../task-stats.service';
import { TaskFocusCounts } from '../task-stats.model';
import {
  DeadlineInfo, PriorityFlag, deadlineInfo, listStatusMeta, priorityFlag,
  PRIORITY_HIGH, PRIORITY_LOW,
} from '../task-meta';

type ViewMode = 'todo' | 'today' | 'completed';
type BandId = 'urgent' | 'high' | 'normal' | 'low';

interface BandDef {
  id: BandId;
  title: string;
}

/** Priority bands, ordered by urgency — the collapsible cards down the page. */
const BANDS: readonly BandDef[] = [
  { id: 'urgent', title: 'Urgent & Overdue' },
  { id: 'high', title: 'High Priority' },
  { id: 'normal', title: 'Normal' },
  { id: 'low', title: 'Low Priority' },
];

/** Band id → its key in the server's focus-counts payload. */
const COUNT_KEY: Record<BandId, keyof TaskFocusCounts> = {
  urgent: 'overdue',
  high: 'high',
  normal: 'normal',
  low: 'low',
};

/** How many tasks to pull for the grouped view — one full page. Matches `max_limit` on the API's
 *  `TaskLimitOffsetPagination`, which silently caps anything larger; asking for more would just
 *  misrepresent how many rows we actually get back. The *counts* come from `/api/task/focus-counts/`
 *  and span the whole set, so they stay exact however far past this window the list runs. */
const FETCH_LIMIT = 200;

/**
 * "Priority Focus" — the redesign's flagship task view. Tasks are grouped into priority bands
 * (overdue first, then High/Normal/Low), each a collapsible card, with a stat-tile summary on top.
 * Reuses the shared task-meta helpers so priority/status/deadline semantics match the rest of the app.
 */
@Component({
  selector: 'app-priority-focus-list',
  imports: [RouterLink, TagColorPipe],
  templateUrl: './priority-focus-list.component.html',
  styleUrls: ['./priority-focus-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PriorityFocusListComponent implements OnInit {
  private readonly taskService = inject(TaskService);
  private readonly tagService = inject(TagService);
  private readonly projectService = inject(ProjectService);
  private readonly statsService = inject(TaskStatsService);
  private readonly drawer = inject(TaskDrawerService);
  private readonly taskEvents = inject(TaskEventsService);

  /** Coalesces live-sync events into one quiet reload (no loading flash). */
  private readonly liveReload$ = new Subject<void>();

  readonly bandDefs = BANDS;
  readonly fetchLimit = FETCH_LIMIT;

  readonly viewMode = signal<ViewMode>('todo');
  readonly loading = signal(true);
  readonly totalCount = signal(0);

  /** True once the filtered set outgrows the window we render — the bands are showing a prefix, so
   *  the page points at the full task list rather than pretending these are all the tasks. */
  readonly hasMore = computed(() => this.totalCount() > FETCH_LIMIT);

  private readonly tasks = signal<Task[]>([]);
  /** Exact counts over the whole filtered set (null until the first response lands). */
  private readonly counts = signal<TaskFocusCounts | null>(null);
  private readonly tags = signal<Tag[]>([]);
  private readonly tagsById = computed(() => new Map(this.tags().map((t) => [t.id, t])));
  private readonly projectNames = signal<Map<number, string>>(new Map());

  readonly collapsed = signal<Record<BandId, boolean>>({
    urgent: false, high: false, normal: true, low: true,
  });

  /** Group the *fetched window* into priority bands: overdue wins, otherwise by priority. These are
   *  the rows we render; the band/tile numbers come from `counts()` and cover the whole set. Keep
   *  this in step with `build_focus_counts` in tasks/api/stats.py. */
  readonly bands = computed(() => {
    const groups: Record<BandId, Task[]> = { urgent: [], high: [], normal: [], low: [] };
    for (const task of this.tasks()) {
      if (deadlineInfo(task)?.state === 'overdue') groups.urgent.push(task);
      else if (task.priority === PRIORITY_HIGH) groups.high.push(task);
      else if (task.priority === PRIORITY_LOW) groups.low.push(task);
      else groups.normal.push(task);
    }
    return groups;
  });

  // --- Stat tiles (server-aggregated over the whole filtered set, not just the fetched window) ---
  readonly overdueCount = computed(() => this.counts()?.overdue ?? this.bands().urgent.length);
  readonly highCount = computed(() => this.counts()?.high ?? this.bands().high.length);
  readonly dueTodayCount = computed(
    () => this.counts()?.due_today ?? this.tasks().filter((t) => this.isDueToday(t)).length);
  private readonly maxTile = computed(() =>
    Math.max(this.overdueCount(), this.highCount(), this.dueTodayCount(), 1));

  /** Stat-tile bar width as a percentage, scaled against the largest of the three tiles. */
  barWidth(n: number): number {
    return n <= 0 ? 0 : Math.max(6, Math.round((n / this.maxTile()) * 100));
  }

  constructor() {
    // Reload when a task is created via the shared drawer (sidebar "New Task" or the FAB).
    this.drawer.created$.pipe(takeUntilDestroyed()).subscribe(() => this.load());
    // Live sync: coalesce remote changes into a quiet reload that keeps the current view on screen.
    this.liveReload$.pipe(debounceTime(300), takeUntilDestroyed()).subscribe(() => this.load(false));
    this.taskEvents.events$.pipe(takeUntilDestroyed()).subscribe((event) => this.onTaskEvent(event));
  }

  /**
   * Apply a live task event. Deletes and updates patch local state for instant feedback; every event
   * then schedules a debounced reload so band membership, ordering, and the server-derived tile
   * counts converge (an update that moves a task between bands, or in/out of the window, settles on
   * the reload). Counts are re-read eagerly since they can't be kept honest locally.
   */
  private onTaskEvent(event: TaskEvent): void {
    switch (event.type) {
      case 'task.deleted':
        this.tasks.update((ts) => ts.filter((t) => t.id !== event.id));
        this.totalCount.update((c) => Math.max(0, c - 1));
        this.loadCounts();
        this.liveReload$.next();
        break;
      case 'task.updated':
        this.tasks.update((ts) => {
          const i = ts.findIndex((t) => t.id === event.id);
          if (i === -1) return ts; // not in the window; the reload will pull it in if it belongs
          const next = [...ts];
          next[i] = { ...event.task, _tags: [] };
          return next;
        });
        this.loadCounts();
        this.liveReload$.next();
        break;
      case 'task.created':
      case 'reconnected':
        this.liveReload$.next();
        break;
    }
  }

  ngOnInit(): void {
    this.tagService.getTags().subscribe((tags) => this.tags.set(tags));
    this.projectService.getProjectsCached().subscribe((projects) =>
      this.projectNames.set(new Map(projects.map((p) => [p.id!, p.title]))),
    );
    this.load();
  }

  setView(mode: ViewMode): void {
    if (mode === this.viewMode()) return;
    this.viewMode.set(mode);
    this.load();
  }

  private load(showLoading = true): void {
    // Live-sync reloads pass showLoading=false so the page doesn't flash its skeleton on every
    // remote change; the initial/explicit loads still show it.
    if (showLoading) this.loading.set(true);
    const filters = this.filtersFor(this.viewMode());
    this.taskService.getTasksPage(filters, 0, FETCH_LIMIT).subscribe((page) => {
      this.tasks.set(page?.results ?? []);
      this.totalCount.set(page?.count ?? 0);
      this.loading.set(false);
    });
    this.loadCounts();
  }

  /** Refresh the exact counts. Cheap (one aggregate query) and independent of the row fetch, so a
   *  failure here just leaves the tiles on their previous values rather than blanking the page. */
  private loadCounts(): void {
    this.statsService.getFocusCounts(this.filtersFor(this.viewMode()))
      .subscribe({ next: (counts) => this.counts.set(counts) });
  }

  private filtersFor(mode: ViewMode): TaskFilters {
    if (mode === 'completed') return new TaskFilters(true);
    if (mode === 'today') return new TaskFilters(null, null, null, null, true);
    return new TaskFilters(false);
  }

  /** The rows to render for a band — only ever the fetched window. */
  tasksIn(id: BandId): Task[] {
    return this.bands()[id];
  }

  /** The band's true size across the whole filtered set (falls back to the window pre-load). */
  countIn(id: BandId): number {
    return this.counts()?.[COUNT_KEY[id]] ?? this.bands()[id].length;
  }

  toggleBand(id: BandId): void {
    this.collapsed.update((state) => ({ ...state, [id]: !state[id] }));
  }

  isCollapsed(id: BandId): boolean {
    return this.collapsed()[id];
  }

  // --- Row helpers (shared semantics with the flat list) ---

  tagsFor(task: Task): Tag[] {
    const byId = this.tagsById();
    return (task.tags ?? []).map((id) => byId.get(id)).filter((t): t is Tag => !!t);
  }

  priorityFlag(task: Task): PriorityFlag {
    return priorityFlag(task.priority);
  }

  statusBadge(task: Task): { label: string; badgeClass: string } | null {
    return listStatusMeta(task.status);
  }

  projectName(task: Task): string {
    return task.project != null ? (this.projectNames().get(task.project) ?? '') : '';
  }

  /** Compact deadline label ("Overdue 2d", "Today 14:00", "Sep 3") with an emphasis class. */
  deadlineLabel(task: Task): { text: string; cls: string } | null {
    const info: DeadlineInfo = deadlineInfo(task);
    if (!info) return null;
    const date = info.date;
    if (info.state === 'overdue') {
      const days = Math.floor((Date.now() - date.getTime()) / 86_400_000);
      return { text: days >= 1 ? `Overdue ${days}d` : 'Overdue', cls: 'is-overdue' };
    }
    if (this.isSameDay(date, new Date())) {
      return { text: `Today ${formatDate(date, 'HH:mm', 'en-US')}`, cls: 'is-soon' };
    }
    if (info.state === 'soon') {
      const days = Math.ceil((date.getTime() - Date.now()) / 86_400_000);
      return { text: `in ${days}d`, cls: 'is-soon' };
    }
    return { text: formatDate(date, 'MMM d', 'en-US'), cls: 'is-upcoming' };
  }

  private isDueToday(task: Task): boolean {
    if (task.completed || !task.end_date) return false;
    const d = new Date(task.end_date);
    return !isNaN(d.getTime()) && this.isSameDay(d, new Date());
  }

  private isSameDay(a: Date, b: Date): boolean {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  // --- Mutations ---

  toggleDone(task: Task): void {
    task.completed = !task.completed;
    if (task.completed && task.for_today) task.for_today = false;
    // Re-read the counts once the write lands: they are server-derived, so unlike the rows below
    // they cannot be kept honest by patching local state.
    this.taskService.updateTask(task).subscribe(() => this.loadCounts());

    const stillMatches = this.viewMode() === 'completed' ? task.completed : !task.completed;
    if (!stillMatches) {
      this.tasks.update((ts) => ts.filter((t) => t.id !== task.id));
      this.totalCount.update((c) => Math.max(0, c - 1));
    } else {
      this.tasks.update((ts) => [...ts]); // re-trigger the band grouping
    }
  }

  openCreate(): void {
    this.drawer.openDrawer();
  }
}
