import {
  ChangeDetectionStrategy, Component, ElementRef, Input, OnDestroy, OnInit, computed, effect, inject, signal,
  untracked, viewChild,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NgClass, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { CdkVirtualScrollViewport, ScrollingModule } from '@angular/cdk/scrolling';
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
import { TaskDrawerService } from '../task-drawer.service';
import { TaskEventsService, TaskEvent } from '../task-events.service';
import { MarkdownComponent } from '../../shared/markdown/markdown.component';
import { KeyboardShortcutsComponent, ShortcutGroup } from '../../shared/keyboard-shortcuts/keyboard-shortcuts.component';
import {
  DeadlineInfo, PriorityFlag, deadlineInfo, listStatusMeta, priorityFlag, priorityRowClass,
} from '../task-meta';

/** `Ctrl+<digit>` → the filter toggle it drives. */
const FILTER_KEYS: { [digit: string]: string } = { '1': 'todo', '2': 'completed', '3': 'today' };

/** Anything that takes typed characters; a bare-key shortcut must never fire from inside one. */
const EDITABLE_SELECTOR = 'input, textarea, select, [contenteditable]:not([contenteditable="false"])';

@Component({
  selector: 'app-task-list',
  imports: [
    FormsModule, NgClass, DatePipe, RouterLink, TagColorPipe, ScrollingModule,
    TaskQuickAddComponent, MarkdownComponent, KeyboardShortcutsComponent,
  ],
  templateUrl: './task-list.component.html',
  styleUrls: ['./task-list.component.css'],
  host: { '(document:keydown)': 'onKeydown($event)' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskListComponent implements OnInit, OnDestroy {
  private readonly breakpointObserver = inject(BreakpointObserver);
  private readonly router = inject(Router);
  private readonly taskDrawer = inject(TaskDrawerService);
  private readonly taskEvents = inject(TaskEventsService);
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

  /** Index of the keyboard-highlighted row in the list, or -1 for none. */
  readonly highlighted = signal(-1);
  readonly shortcutsOpen = signal(false);

  private readonly viewport = viewChild(CdkVirtualScrollViewport);
  private readonly searchBox = viewChild<ElementRef<HTMLInputElement>>('searchBox');
  private readonly quickAdd = viewChild(TaskQuickAddComponent);

  @Input() filters_tags: Tag[] | null = null;
  @Input() for_tag: Tag | null = null;

  private _project: number | null = null;

  /**
   * Scope the list to one project (the project detail view). Beyond filtering, it becomes the
   * default project for anything created from this list, so a task added inside a project lands
   * in it without the user picking it.
   */
  @Input()
  set project(value: number | null | undefined) {
    const next = value ?? null;
    if (next === this._project) return;
    this._project = next;
    // Only rebuild once the list exists; before ngOnInit the first build picks this up anyway.
    if (this.dataSource()) this.rebuild();
  }

  get project(): number | null {
    return this._project;
  }

  private readonly search$ = new Subject<string>();
  /** Coalesces live-sync events into one server reconcile (a burst of edits → a single refetch). */
  private readonly liveRefresh$ = new Subject<void>();
  private readonly subscription = new Subscription();

  constructor(
    private taskService: TaskService,
    private tagService: TagService,
    private projectService: ProjectService,
  ) {
    // Keep the highlight inside the list as it shrinks under it (a row deleted, completed, or
    // filtered away). The count settles asynchronously, off the server, so this can't be a
    // one-shot clamp at the call site.
    effect(() => {
      const last = this.totalCount() - 1;
      untracked(() => {
        if (this.highlighted() > last) this.highlighted.set(Math.max(-1, last));
      });
    });
  }

  ngOnInit(): void {
    this.getTags();
    this.getProjects();
    this.subscription.add(
      this.search$.pipe(debounceTime(250), distinctUntilChanged()).subscribe(() => this.rebuild())
    );
    // Live sync: reconcile the loaded window with the server after a burst of remote changes.
    this.subscription.add(
      this.liveRefresh$.pipe(debounceTime(300)).subscribe(() => this.dataSource()?.refresh())
    );
    this.subscription.add(
      this.taskEvents.events$.subscribe((event) => this.onTaskEvent(event))
    );
    // A task created through the shared drawer belongs in this list too — reconcile without
    // waiting on the live-sync socket, which may be down.
    this.subscription.add(
      this.taskDrawer.created$.subscribe(() => this.dataSource()?.refresh())
    );
    this.rebuild();
  }

  /**
   * Apply a live task event to the loaded window. Deletes shrink the list immediately; updates patch
   * the row in place for instant feedback; everything then triggers a debounced server reconcile so
   * filter-match, ordering, and out-of-window inserts converge (a task that no longer matches the
   * active filters drops out on the refetch).
   */
  private onTaskEvent(event: TaskEvent): void {
    const ds = this.dataSource();
    if (!ds) return;
    switch (event.type) {
      case 'task.deleted':
        ds.removeById(event.id);
        this.totalCount.update((c) => Math.max(0, c - 1));
        break;
      case 'task.updated':
        ds.replace({ ...event.task, _tags: [] });
        this.liveRefresh$.next();
        break;
      case 'task.created':
      case 'reconnected':
        this.liveRefresh$.next();
        break;
    }
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
    const filters = this.buildStateFilters();
    filters.project = this._project;
    return filters;
  }

  private buildStateFilters(): TaskFilters {
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
    // Row indices are only meaningful for one query, so the highlight doesn't survive a rebuild.
    this.highlighted.set(-1);
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
      // An explicit `@project` token wins; otherwise a project-scoped list adds into its project.
      project: request.project ?? this._project ?? undefined,
      // Only set when the shortcut syntax asked for it, so the backend defaults still apply.
      priority: request.priority,
      end_date: request.endDate,
      tags: [],
      _tags: request.tags,
    };
    this.taskService.addTask(task).subscribe(() => this.rebuild());
  }

  deleteTask(task: Task): void {
    if (task.id == null) return;
    this.taskService.deleteTask(task.id).subscribe(() => {
      this.dataSource()?.removeById(task.id);
      this.totalCount.update(c => Math.max(0, c - 1));
    });
  }

  toggleTaskDone(task: Task): void {
    if (!task) return;
    task.completed = !task.completed;
    if (task.completed && task.for_today) task.for_today = false;

    const f = this.filters();
    const showsBothStates = f['todo'] && f['completed'];
    const staysInList = showsBothStates && !f['today'];

    this.applyAfterWrite(task, staysInList);
  }

  toggleTaskToday(task: Task): void {
    if (!task || task.completed) return;
    task.for_today = !task.for_today;

    const staysInList = !(this.filters()['today'] && !task.for_today);

    this.applyAfterWrite(task, staysInList);
  }

  /**
   * Persist a toggled task, then fold it back into the list.
   *
   * The list is only touched once the write has landed. `removeById` revalidates the visible range
   * against the server, so a refetch fired while the PATCH is still in flight reads the task back
   * in its pre-toggle state and puts the row straight back on screen.
   */
  private applyAfterWrite(task: Task, staysInList: boolean): void {
    this.taskService.updateTask(task).subscribe(() => {
      if (staysInList) {
        this.dataSource()?.replace(task);
      } else {
        this.dataSource()?.removeById(task.id);
      }
    });
  }

  trackByIndex(index: number): number {
    return index;
  }

  // --- Keyboard shortcuts ---

  readonly shortcutGroups: ShortcutGroup[] = [
    {
      title: 'Navigation',
      items: [
        { keys: ['↑'], label: 'Highlight the previous task' },
        { keys: ['↓'], label: 'Highlight the next task' },
        { keys: ['/'], label: 'Search tasks' },
        { keys: ['c'], label: 'Add a task' },
      ],
    },
    {
      title: 'Highlighted task',
      items: [
        { keys: ['Enter'], label: 'Toggle done / not done' },
        { keys: ['e'], label: 'Edit the task' },
        { keys: ['t'], label: 'Toggle today' },
        { keys: ['Delete'], label: 'Delete the task' },
      ],
    },
    {
      title: 'Filters',
      items: [
        { keys: ['Ctrl', '1'], label: 'Show / hide todo tasks' },
        { keys: ['Ctrl', '2'], label: 'Show / hide completed tasks' },
        { keys: ['Ctrl', '3'], label: 'Show / hide today’s tasks' },
      ],
    },
    {
      title: 'Help',
      items: [
        { keys: ['?'], label: 'Open this panel' },
        { keys: ['Esc'], label: 'Close the panel / leave the field' },
      ],
    },
  ];

  onKeydown(event: KeyboardEvent): void {
    if (event.defaultPrevented) return;

    // A modal owns the keyboard while it is up. The create-task drawer is mounted app-wide, so it
    // can be open *over* this list — without this the list would still act on keys pressed while
    // focus sits on one of the drawer's buttons (or on nothing at all). Both close on Escape.
    if (this.taskDrawer.open()) return;
    if (this.shortcutsOpen()) {
      if (event.key === '?') {
        event.preventDefault();
        this.shortcutsOpen.set(false);
      }
      return;
    }

    // Ctrl/Cmd+1..3 drive the filter toggles. Safe to handle even mid-typing: they emit no text.
    const filter = (event.ctrlKey || event.metaKey) && !event.altKey ? FILTER_KEYS[event.key] : undefined;
    if (filter) {
      event.preventDefault();
      this.toggleFilters(filter);
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey) return;

    // Everything below is a bare, unmodified key, so it competes with typing. If the user is in a
    // field, none of it may fire — Escape just gets them back out. Keep this the last thing before
    // the switch, so any shortcut added later is guarded by construction.
    if (this.isTyping(event)) {
      if (event.key === 'Escape') this.activeElement()?.blur();
      return;
    }

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.moveHighlight(1);
        return;
      case 'ArrowUp':
        event.preventDefault();
        this.moveHighlight(-1);
        return;
      case '/':
        event.preventDefault();
        this.focusSearch();
        return;
      case 'c':
        event.preventDefault();
        this.quickAdd()?.focus();
        return;
      case '?':
        event.preventDefault();
        this.shortcutsOpen.set(true);
        return;
      case 'Escape':
        this.highlighted.set(-1);
        return;
    }

    const task = this.highlightedTask();
    if (!task) return;

    switch (event.key) {
      case 'Enter':
        event.preventDefault();
        this.toggleTaskDone(task);
        return;
      case 'e':
        event.preventDefault();
        this.router.navigate(['/tasks', task.id]);
        return;
      case 't':
        event.preventDefault();
        this.toggleTaskToday(task);
        return;
      case 'Delete':
        event.preventDefault();
        this.deleteTask(task);
        return;
    }
  }

  /** Highlight a row from the pointer, so a click hands the cursor over to the keyboard. */
  highlight(index: number): void {
    this.highlighted.set(index);
  }

  /** The task under the highlight, or undefined when nothing is highlighted (or its page is still loading). */
  private highlightedTask(): Task | undefined {
    return this.dataSource()?.taskAt(this.highlighted());
  }

  private moveHighlight(delta: number): void {
    const last = this.totalCount() - 1;
    if (last < 0) {
      this.highlighted.set(-1);
      return;
    }
    const current = this.highlighted();
    const next = current < 0 ? 0 : Math.min(last, Math.max(0, current + delta));
    this.highlighted.set(next);
    this.scrollIntoView(next);
  }

  /**
   * Scroll the row at `index` just into view, leaving the viewport alone when it already is.
   * Rows are a fixed height, so the offsets are arithmetic — no DOM measuring of the row itself,
   * which also means this works for rows the virtual scroller hasn't rendered (or fetched) yet.
   */
  private scrollIntoView(index: number): void {
    const viewport = this.viewport();
    if (!viewport) return;
    const height = this.rowHeight();
    const top = index * height;
    const offset = viewport.measureScrollOffset();
    const size = viewport.getViewportSize();
    if (top < offset) {
      viewport.scrollToOffset(top);
    } else if (top + height > offset + size) {
      viewport.scrollToOffset(top + height - size);
    }
  }

  private focusSearch(): void {
    const input = this.searchBox()?.nativeElement;
    input?.focus();
    input?.select();
  }

  /**
   * Is the user typing into something?
   *
   * Checks the event's target *and* the focused element: a control may retarget the event at its
   * host (custom elements, ngx-chips), in which case the target alone isn't a field but the focused
   * element is. `closest` rather than a tag check, so a caret inside a contenteditable's child
   * element still counts.
   */
  private isTyping(event: KeyboardEvent): boolean {
    return this.isEditable(event.target) || this.isEditable(this.activeElement());
  }

  private isEditable(target: EventTarget | null): boolean {
    const el = target as Element | null;
    return typeof el?.closest === 'function' && el.closest(EDITABLE_SELECTOR) !== null;
  }

  private activeElement(): HTMLElement | null {
    return document.activeElement as HTMLElement | null;
  }

  protected readonly TASK_PAGE_SIZE = TASK_PAGE_SIZE;
}
