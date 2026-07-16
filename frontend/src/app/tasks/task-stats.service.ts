import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { ServiceBase } from '../service-base';
import { MessageService } from '../message.service';
import { TaskFilters } from './task-filters';
import { TaskFocusCounts, TaskStats } from './task-stats.model';

@Injectable({ providedIn: 'root' })
export class TaskStatsService extends ServiceBase {
  private http = inject(HttpClient);
  private statsURL = `${environment.apiBase}/api/task/stats/`;
  private focusCountsURL = `${environment.apiBase}/api/task/focus-counts/`;

  constructor(protected override messageService: MessageService) {
    super(messageService);
  }

  /** Fetch aggregated stats for a filter set. Uses the same `TaskFilters` query contract as the
   *  task list, so the stats honour identical filters. `bucket` selects day/week time grouping. */
  getStats(filters: TaskFilters, bucket: 'day' | 'week'): Observable<TaskStats> {
    const base = filters.getFilteredURL(this.statsURL);
    const sep = base.includes('?') ? '&' : '?';
    return this.http
      .get<TaskStats>(`${base}${sep}bucket=${bucket}`)
      .pipe(tap(() => this.log(`fetched task stats (${bucket})`)));
  }

  /** Exact priority-band + tile counts for a filter set. The Priority Focus list only fetches one
   *  page of tasks, so it sources its counts here rather than counting the rows it rendered. */
  getFocusCounts(filters: TaskFilters): Observable<TaskFocusCounts> {
    return this.http
      .get<TaskFocusCounts>(filters.getFilteredURL(this.focusCountsURL))
      .pipe(tap((c) => this.log(`fetched focus counts (${c.total} tasks)`)));
  }
}
