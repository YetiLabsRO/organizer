import { CollectionViewer, DataSource, ListRange } from '@angular/cdk/collections';
import { BehaviorSubject, Observable, Subscription } from 'rxjs';
import { Page } from '../page';
import { Task } from './task';

/** Rows fetched per request; matches the backend default page size. */
export const TASK_PAGE_SIZE = 50;

/** Extra pages fetched on each side of the visible range (the "and a bit more" window). */
const BUFFER_PAGES = 1;

/** Loads one page of tasks: `(offset, limit) => Page<Task>`. */
export type TaskPageLoader = (offset: number, limit: number) => Observable<Page<Task>>;

/**
 * A CDK `DataSource` that loads tasks on demand as the viewport scrolls.
 *
 * It keeps a sparse array sized to the server's total `count`; entries are
 * `undefined` until their page is fetched (rendered as skeleton rows). On every
 * viewport range change it fetches the pages overlapping the visible range plus
 * a one-page buffer on each side, so only what's on (or near) screen is ever in
 * memory — regardless of whether the user has 10 tasks or 100 000.
 */
export class TaskDataSource extends DataSource<Task | undefined> {
  private readonly pageSize = TASK_PAGE_SIZE;
  private cachedData: (Task | undefined)[] = [];
  private readonly fetchedPages = new Set<number>();
  private readonly dataStream = new BehaviorSubject<(Task | undefined)[]>([]);
  private readonly subscription = new Subscription();
  private lastRange: ListRange = { start: 0, end: this.pageSize };
  private total = 0;
  private initialised = false;

  constructor(private readonly loader: TaskPageLoader) {
    super();
  }

  /** Total number of tasks matching the current filter (server `count`). */
  get totalCount(): number {
    return this.total;
  }

  connect(collectionViewer: CollectionViewer): Observable<(Task | undefined)[]> {
    this.subscription.add(
      collectionViewer.viewChange.subscribe((range: ListRange) => {
        this.lastRange = range;
        this.fetchRange(range);
      }),
    );
    // Kick off the first page so the viewport has something to size against.
    this.fetchPage(0);
    return this.dataStream;
  }

  disconnect(): void {
    this.subscription.unsubscribe();
  }

  /** Clear all loaded data and re-fetch the currently visible window in place. */
  reset(): void {
    this.fetchedPages.clear();
    this.cachedData = [];
    this.total = 0;
    this.initialised = false;
    this.dataStream.next(this.cachedData);
    this.fetchPage(0);
    this.fetchRange(this.lastRange);
  }

  /** The task at `index`, or `undefined` while its page is still loading (or out of bounds). */
  taskAt(index: number): Task | undefined {
    return index >= 0 ? this.cachedData[index] : undefined;
  }

  /** Replace a task in place (e.g. after toggling it, when it stays in view). */
  replace(task: Task): void {
    const index = this.cachedData.findIndex((t) => t?.id === task.id);
    if (index !== -1) {
      this.cachedData[index] = task;
      this.dataStream.next(this.cachedData);
    }
  }

  /**
   * Optimistically drop a task by id: splice it out and shift the total down.
   * Fetched-page tracking is cleared so the visible range revalidates against
   * the server and converges — giving instant feedback without a full reset.
   */
  removeById(id: number | undefined): void {
    const index = this.cachedData.findIndex((t) => t?.id === id);
    if (index === -1) {
      return;
    }
    this.cachedData.splice(index, 1);
    if (this.total > 0) {
      this.total -= 1;
    }
    this.fetchedPages.clear();
    this.dataStream.next(this.cachedData);
    this.fetchRange(this.lastRange);
  }

  private fetchRange(range: ListRange): void {
    const startPage = this.pageOf(range.start);
    const endPage = this.pageOf(Math.max(range.start, range.end - 1));
    for (let page = startPage - BUFFER_PAGES; page <= endPage + BUFFER_PAGES; page++) {
      if (page >= 0) {
        this.fetchPage(page);
      }
    }
  }

  private pageOf(index: number): number {
    return Math.max(0, Math.floor(index / this.pageSize));
  }

  private fetchPage(page: number): void {
    if (this.fetchedPages.has(page)) {
      return;
    }
    if (this.initialised && page * this.pageSize >= this.total) {
      return;
    }
    this.fetchedPages.add(page);
    this.loader(page * this.pageSize, this.pageSize).subscribe({
      next: (result: Page<Task>) => {
        if (!result) {
          this.fetchedPages.delete(page);
          return;
        }
        if (!this.initialised) {
          this.total = result.count;
          this.cachedData = new Array<Task | undefined>(result.count);
          this.initialised = true;
        }
        result.results.forEach((task, i) => {
          this.cachedData[page * this.pageSize + i] = task;
        });
        this.dataStream.next(this.cachedData);
      },
      error: () => {
        // Allow a retry on the next range change.
        this.fetchedPages.delete(page);
      },
    });
  }
}
