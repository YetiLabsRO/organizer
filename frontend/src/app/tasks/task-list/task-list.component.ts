import { ChangeDetectionStrategy, Component, Input, OnDestroy, OnInit, signal } from '@angular/core';
import { NgClass, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ScrollingModule } from '@angular/cdk/scrolling';
import { Subject, Subscription } from 'rxjs';
import { debounceTime, distinctUntilChanged, tap } from 'rxjs/operators';
import { TaskService } from '../task.service';
import { Task } from '../task';
import { TagService } from '../../tags/tag.service';
import { Tag } from '../../tags/tag';
import { TagColorPipe } from '../../tags/tag-color.pipe';
import { TaskFilters } from '../task-filters';
import { TaskDataSource, TaskPageLoader, TASK_PAGE_SIZE } from '../task-data-source';

@Component({
  selector: 'app-task-list',
  imports: [FormsModule, NgClass, DatePipe, RouterLink, TagColorPipe, ScrollingModule],
  templateUrl: './task-list.component.html',
  styleUrls: ['./task-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskListComponent implements OnInit, OnDestroy {
  /** Fixed row height (px) — required by the CDK fixed-size virtual scroll strategy. */
  readonly rowHeight = 64;

  readonly dataSource = signal<TaskDataSource | null>(null);
  readonly tags = signal<Tag[]>([]);
  readonly totalCount = signal(0);
  readonly filters = signal<{ [k: string]: boolean }>({ today: false, completed: false, todo: true });

  taskInput = '';
  searchInput = '';

  @Input() filters_tags: Tag[] | null = null;
  @Input() for_tag: Tag | null = null;

  private readonly search$ = new Subject<string>();
  private readonly subscription = new Subscription();

  constructor(
    private taskService: TaskService,
    private tagService: TagService
  ) { }

  ngOnInit(): void {
    this.getTags();
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

  /** Translate the UI filter toggles + search term into a single paginable query. */
  private buildFilters(): TaskFilters {
    const f = this.filters();
    let completed: boolean | null = null;
    if (f['completed'] != f['todo']) {
      completed = f['completed'];
    }
    const tags: Tag[] | null = this.filters_tags || null;
    const contains: string | null = this.searchInput.trim() || null;

    // "today + completed" = tasks flagged for today OR completed today, honoured server-side in a
    // single query via `today_view` (replaces the old two-call merge so it stays paginable).
    if (f['today'] && f['completed']) {
      return new TaskFilters(completed, contains, null, tags, null, true);
    }

    const forToday: boolean | null = f['today'] ? true : null;
    return new TaskFilters(completed, contains, null, tags, forToday, null);
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

  addTask(taskDescription: string): void {
    const tag_re = /^(?<title>.+?)(@tags\((?<tags>[\w ,-]+)\))?$/ui;
    const matches = taskDescription.match(tag_re);

    const tags: string | undefined = matches?.groups?.tags;
    const title: string | undefined = matches?.groups?.title;

    if (!title) {
      return;
    }

    const task: Task = {
      title: title,
      for_today: this.filters()['today'],
      tags: [],
      _tags: []
    };

    this.taskInput = '';

    if (tags === undefined) {
      this.taskService.addTask(task).subscribe(() => this.rebuild());
      return;
    }

    const parsed_tags: string[] = tags.split(/\s*(?:,|$)\s*/);
    parsed_tags.forEach((tag: string) => {
      this.tagService.getTagBySlug(tag).subscribe((found: Tag[]) => {
        if (found.length) {
          task.tags.push(found[0].id!);
          task._tags.push(found[0]);
        }
      });
    });
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
