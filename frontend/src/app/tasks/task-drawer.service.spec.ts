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

  it('openDrawer carries a preset for the drawer to seed its draft with', () => {
    service.openDrawer({ project: 3 });

    expect(service.open()).toBe(true);
    expect(service.preset()).toEqual({ project: 3 });
  });

  it('opening without a preset clears the previous one', () => {
    service.openDrawer({ project: 3 });
    service.openDrawer();

    expect(service.preset()).toEqual({});
  });

  it('notifyCreated emits the created task to subscribers', () => {
    const seen: Task[] = [];
    service.created$.subscribe((task) => seen.push(task));

    const task: Task = { title: 'Refactor auth', tags: [], _tags: [] };
    service.notifyCreated(task);

    expect(seen).toEqual([task]);
  });
});
