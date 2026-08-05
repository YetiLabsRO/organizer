import { Injectable, signal } from '@angular/core';
import { Subject } from 'rxjs';

import { Task } from './task';

/** Fields a trigger can pre-fill on the drawer's draft when opening it. */
export interface TaskDraftPreset {
  /** Pre-select a project — the project detail view opens the drawer with its own project. */
  project?: number;
}

/**
 * App-wide handle for the single Create Task drawer mounted in the shell. Any trigger
 * (the sidebar "New Task" button, a list FAB) calls `openDrawer()`; interested lists
 * subscribe to `created$` to refresh when a task is added from anywhere.
 */
@Injectable({ providedIn: 'root' })
export class TaskDrawerService {
  /** Two-way bound to the mounted drawer's `open` model. */
  readonly open = signal(false);

  /** What the next opening seeds its draft with — set by the trigger, read by the drawer. */
  readonly preset = signal<TaskDraftPreset>({});

  private readonly createdSubject = new Subject<Task>();
  /** Emits each time the drawer creates a task. */
  readonly created$ = this.createdSubject.asObservable();

  openDrawer(preset: TaskDraftPreset = {}): void {
    this.preset.set(preset);
    this.open.set(true);
  }

  notifyCreated(task: Task): void {
    this.createdSubject.next(task);
  }
}
