import { ChangeDetectionStrategy, Component, Input, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NgClass, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ScrollingModule } from '@angular/cdk/scrolling';
import { BreakpointObserver } from '@angular/cdk/layout';
import { Subject, Subscription } from 'rxjs';
import { debounceTime, distinctUntilChanged, map, tap } from 'rxjs/operators';
import { TaskService } from '../task.service';
import { Task } from '../task';
import { TagService } from '../../tags/tag.service';
import { Tag } from '../../tags/tag';
import { TagColorPipe } from '../../tags/tag-color.pipe';
import { ProjectService } from '../../projects/project.service';
import { TaskFilters } from '../task-filters';
import { TaskDataSource, TaskPageLoader, TASK_PAGE_SIZE } from '../task-data-source';
import { TaskQuickAddComponent, NewTaskRequest } from '../task-quick-add/task-quick-add.component';
import { MarkdownComponent } from '../../shared/markdown/markdown.component';
import {
  DeadlineInfo, PriorityFlag, deadlineInfo, listStatusMeta, priorityFlag, priorityRowClass,
} from '../task-meta';

@Component({
  selector: 'app-task-list',
  imports: [
    FormsModule, NgClass, DatePipe, RouterLink, TagColorPipe, ScrollingModule,
    TaskQuickAddComponent, MarkdownComponent,
  ],
  templateUrl: './task-list.component.html',
  styleUrls: ['./task-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskListComponent implements OnInit, OnDestroy {
  private readonly breakpointObserver = inject(BreakpointObserver);
  readonly isMobile = toSignal(
    this.breakpointObserver.observe('(max-width: 767.98px)').pipe(map((r) => r.matches)),
    { initialValue: false },
  );
  /** Fixed row height (px). Compact on desktop; taller on mobile so the title (up to two lines),
   *  the priority/status/deadline meta line, and the tag dots all fit. */
  readonly rowHeight = computed(() => (this.isMobile() ? 96 : 56));

  readonly dataSource = signal<TaskDataSource | null>(null);
  readonly tags = signal<Tag[]>([]);
  readonly totalCount = signal(0);
  readonly filters = signal<{ [k: string]: boolean }>({ today: false, completed: false, todo: true });
  /** Tags chosen by clicking pills in the list — combined with AND (a task must have all of them). */
  readonly activeTags = signal<Tag[]>([]);
  /** id → project title, so a row can show its project without a per-row fetch. */
  private readonly projectNames = signal<Map<number, string>>(new Map());

  /** id → Tag lookup built from all loaded tags; drives reactive per-row tag rendering. */
  private readonly tagsById = computed(() => new Map(this.tags().map((t) => [t.id, t])));

  searchInput = '';

  @Input() filters_tags: Tag[] | null = null;
  @Input() for_tag: Tag | null = null;

  private readonly search$ = new Subject<string>();
  private readonly subscription = new Subscription();

  constructor(
    private taskService: TaskService,
    private tagService: TagService,
    private projectService: ProjectService,
  ) { }

  ngOnInit(): void {
    this.getTags();
    this.getProjects();
    this.subscription.add(
      this.search$.pipe(debounceTime(250), distinctUntilChanged()).subscribe(() => this.rebuild())
    );
    this.rebuild();
  }

  ngOnDestroy(): void {
    this.subscription.unsubscribe();
  }

  onSearch(term: string): void {
    this.searchInput = term;
    this.search$.next(term.trim());
  }

  toggleFilters(filter: string): void {
    const current = this.filters();
    if (!(filter in current)) return;
    this.filters.set({ ...current, [filter]: !current[filter] });
    this.rebuild();
  }

  /** Add a tag to the active AND-filter (clicking a pill on a task). */
  filterByTag(tag: Tag): void {
    if (this.activeTags().some((t) => t.id === tag.id)) return;
    this.activeTags.update((tags) => [...tags, tag]);
    this.rebuild();
  }

  removeTagFilter(tag: Tag): void {
    this.activeTags.update((tags) => tags.filter((t) => t.id !== tag.id));
    this.rebuild();
  }

  clearTagFilter(): void {
    this.activeTags.set([]);
    this.rebuild();
  }

  /** Resolve a task's tag ids to Tag objects via the loaded tag map (reactive — all rows update). */
  tagsFor(task: Task): Tag[] {
    const byId = this.tagsById();
    return (task.tags ?? [])
      .map((id) => byId.get(id))
      .filter((tag): tag is Tag => !!tag);
  }

  /** Translate the UI filter toggles + search term into a single paginable query. */
  private buildFilters(): TaskFilters {
    const f = this.filters();
    let completed: boolean | null = null;
    if (f['completed'] != f['todo']) {
      completed = f['completed'];
    }
    // AND all tag constraints: any tags passed in (e.g. the tag detail page) plus clicked pills.
    const combined = [...(this.filters_tags ?? []), ...this.activeTags()];
    const deduped = combined.filter((t, i, arr) => arr.findIndex((x) => x.id === t.id) === i);
    const tags: Tag[] | null = deduped.length ? deduped : null;
    const contains: string | null = this.searchInput.trim() || null;

    // "today + completed" = tasks flagged for today OR completed today, honoured server-side in a
    // single query via `today_view` (replaces the old two-call merge so it stays paginable).
    if (f['today'] && f['completed']) {
      return new TaskFilters(completed, contains, null, tags, null, true);
    }

    const forToday: boolean | null = f['today'] ? true : null;
    return new TaskFilters(completed, contains, null, tags, forToday, null);
  }

  /** Query params for the stats page so it opens with the list's currently active filters. */
  get statsQueryParams(): { [k: string]: string | string[] } {
    return this.buildFilters().getQueryParams();
  }

  private makeLoader(): TaskPageLoader {
    const filters = this.buildFilters();
    return (offset: number, limit: number) =>
      this.taskService.getTasksPage(filters, offset, limit).pipe(
        tap(page => { if (page) this.totalCount.set(page.count); })
      );
  }

  /** Rebuild the windowed data source for the current filters/search (resets to the top). */
  private rebuild(): void {
    this.dataSource.set(new TaskDataSource(this.makeLoader()));
  }

  getTags(): void {
    this.tagService.getTags()
      .subscribe(tags => this.tags.set(tags));
  }

  getProjects(): void {
    this.projectService.getProjectsCached().subscribe((projects) =>
      this.projectNames.set(new Map(projects.map((p) => [p.id!, p.title]))),
    );
  }

  // --- Per-row metadata for the richer list (priority / status / deadline / project) ---

  /** Row accent class keyed off priority. */
  rowClass(task: Task): string {
    return priorityRowClass(task.priority);
  }

  /** Flag icon for high/low priority (null for neutral). */
  priorityFlag(task: Task): PriorityFlag {
    return priorityFlag(task.priority);
  }

  /** Status badge for the row (null for the default "Idea"). */
  statusBadge(task: Task): { label: string; badgeClass: string } | null {
    return listStatusMeta(task.status);
  }

  /** Deadline classification for overdue/soon emphasis (null when completed/undated). */
  deadline(task: Task): DeadlineInfo {
    return deadlineInfo(task);
  }

  /** Resolve a task's project id to its title (empty when none/unloaded). */
  projectName(task: Task): string {
    return task.project != null ? (this.projectNames().get(task.project) ?? '') : '';
  }

  onQuickAdd(request: NewTaskRequest): void {
    const task: Task = {
      title: request.title,
      for_today: this.filters()['today'],
      project: request.project,
      // Only set when the shortcut syntax asked for it, so the backend defaults still apply.
      priority: request.priority,
      end_date: request.endDate,
      tags: [],
      _tags: request.tags,
    };
    this.taskService.addTask(task).subscribe(() => this.rebuild());
  }

  deleteTask(task: Task): void {
    if (task.id != null) {
      this.taskService.deleteTask(task.id).subscribe();
    }
    this.dataSource()?.removeById(task.id);
    this.totalCount.update(c => Math.max(0, c - 1));
  }

  toggleTaskDone(task: Task): void {
    if (!task) return;
    task.completed = !task.completed;
    if (task.completed && task.for_today) task.for_today = false;
    this.taskService.updateTask(task).subscribe();

    const f = this.filters();
    const showsBothStates = f['todo'] && f['completed'];
    if (showsBothStates && !f['today']) {
      this.dataSource()?.replace(task);
    } else {
      // removeById self-heals: if the task still matches, the range refetch brings it back.
      this.dataSource()?.removeById(task.id);
    }
  }

  toggleTaskToday(task: Task): void {
    if (!task || task.completed) return;
    task.for_today = !task.for_today;
    this.taskService.updateTask(task).subscribe();

    if (this.filters()['today'] && !task.for_today) {
      this.dataSource()?.removeById(task.id);
    } else {
      this.dataSource()?.replace(task);
    }
  }

  trackByIndex(index: number): number {
    return index;
  }

  protected readonly TASK_PAGE_SIZE = TASK_PAGE_SIZE;
}
