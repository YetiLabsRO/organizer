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
import { TaskCreateDrawerComponent } from '../task-create-drawer/task-create-drawer.component';
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

/** How many tasks to pull for the grouped view. A personal organizer's actionable set is small;
 *  we fetch a generous window and group client-side so the bands are exact and mutually exclusive. */
const FETCH_LIMIT = 500;

/**
 * "Priority Focus" — the redesign's flagship task view. Tasks are grouped into priority bands
 * (overdue first, then High/Normal/Low), each a collapsible card, with a stat-tile summary on top.
 * Reuses the shared task-meta helpers so priority/status/deadline semantics match the rest of the app.
 */
@Component({
  selector: 'app-priority-focus-list',
  imports: [RouterLink, TagColorPipe, TaskCreateDrawerComponent],
  templateUrl: './priority-focus-list.component.html',
  styleUrls: ['./priority-focus-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PriorityFocusListComponent implements OnInit {
  private readonly taskService = inject(TaskService);
  private readonly tagService = inject(TagService);
  private readonly projectService = inject(ProjectService);

  readonly bandDefs = BANDS;

  readonly viewMode = signal<ViewMode>('todo');
  readonly loading = signal(true);
  readonly totalCount = signal(0);

  private readonly tasks = signal<Task[]>([]);
  private readonly tags = signal<Tag[]>([]);
  private readonly tagsById = computed(() => new Map(this.tags().map((t) => [t.id, t])));
  private readonly projectNames = signal<Map<number, string>>(new Map());

  readonly drawerOpen = signal(false);
  readonly collapsed = signal<Record<BandId, boolean>>({
    urgent: false, high: false, normal: true, low: true,
  });

  /** Group the loaded tasks into priority bands: overdue wins, otherwise by priority. */
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

  // --- Stat tiles (derived from the loaded set) ---
  readonly overdueCount = computed(() => this.bands().urgent.length);
  readonly highCount = computed(() => this.bands().high.length);
  readonly dueTodayCount = computed(() => this.tasks().filter((t) => this.isDueToday(t)).length);
  private readonly maxTile = computed(() =>
    Math.max(this.overdueCount(), this.highCount(), this.dueTodayCount(), 1));

  /** Stat-tile bar width as a percentage, scaled against the largest of the three tiles. */
  barWidth(n: number): number {
    return n <= 0 ? 0 : Math.max(6, Math.round((n / this.maxTile()) * 100));
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

  private load(): void {
    this.loading.set(true);
    this.taskService.getTasksPage(this.filtersFor(this.viewMode()), 0, FETCH_LIMIT).subscribe((page) => {
      this.tasks.set(page?.results ?? []);
      this.totalCount.set(page?.count ?? 0);
      this.loading.set(false);
    });
  }

  private filtersFor(mode: ViewMode): TaskFilters {
    if (mode === 'completed') return new TaskFilters(true);
    if (mode === 'today') return new TaskFilters(null, null, null, null, true);
    return new TaskFilters(false);
  }

  tasksIn(id: BandId): Task[] {
    return this.bands()[id];
  }

  countIn(id: BandId): number {
    return this.bands()[id].length;
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
    this.taskService.updateTask(task).subscribe();

    const stillMatches = this.viewMode() === 'completed' ? task.completed : !task.completed;
    if (!stillMatches) {
      this.tasks.update((ts) => ts.filter((t) => t.id !== task.id));
      this.totalCount.update((c) => Math.max(0, c - 1));
    } else {
      this.tasks.update((ts) => [...ts]); // re-trigger the band grouping
    }
  }

  openCreate(): void {
    this.drawerOpen.set(true);
  }

  /** A task was created in the drawer — refresh the current view so it appears in its band. */
  onCreated(): void {
    this.load();
  }
}
