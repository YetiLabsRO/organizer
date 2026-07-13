import { Injectable, signal } from '@angular/core';
import { Subject } from 'rxjs';

import { Task } from './task';

/**
 * App-wide handle for the single Create Task drawer mounted in the shell. Any trigger
 * (the sidebar "New Task" button, a list FAB) calls `openDrawer()`; interested lists
 * subscribe to `created$` to refresh when a task is added from anywhere.
 */
@Injectable({ providedIn: 'root' })
export class TaskDrawerService {
  /** Two-way bound to the mounted drawer's `open` model. */
  readonly open = signal(false);

  private readonly createdSubject = new Subject<Task>();
  /** Emits each time the drawer creates a task. */
  readonly created$ = this.createdSubject.asObservable();

  openDrawer(): void {
    this.open.set(true);
  }

  notifyCreated(task: Task): void {
    this.createdSubject.next(task);
  }
}
