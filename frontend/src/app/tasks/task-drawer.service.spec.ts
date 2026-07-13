import { TestBed } from '@angular/core/testing';

import { TaskDrawerService } from './task-drawer.service';
import { Task } from './task';

describe('TaskDrawerService', () => {
  let service: TaskDrawerService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(TaskDrawerService);
  });

  it('starts closed', () => {
    expect(service.open()).toBe(false);
  });

  it('openDrawer opens the drawer', () => {
    service.openDrawer();
    expect(service.open()).toBe(true);
  });

  it('notifyCreated emits the created task to subscribers', () => {
    const seen: Task[] = [];
    service.created$.subscribe((task) => seen.push(task));

    const task: Task = { title: 'Refactor auth', tags: [], _tags: [] };
    service.notifyCreated(task);

    expect(seen).toEqual([task]);
  });
});
