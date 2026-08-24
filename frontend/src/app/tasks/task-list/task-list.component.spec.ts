import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Router, provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { CollectionViewer } from '@angular/cdk/collections';
import { Subject, of } from 'rxjs';

import { TaskListComponent } from './task-list.component';
import { TaskService } from '../task.service';
import { TaskDrawerService } from '../task-drawer.service';
import { TaskDataSource } from '../task-data-source';
import { Task } from '../task';

function makeTask(id: number, overrides: Partial<Task> = {}): Task {
  return { id, title: `Task ${id}`, completed: false, for_today: false, tags: [], _tags: [], ...overrides };
}

/** Press a key on the document, as the component's host listener sees it. */
function press(key: string, init: KeyboardEventInit = {}, target: EventTarget = document.body): void {
  target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init }));
}

describe('TaskListComponent', () => {
  let component: TaskListComponent;
  let fixture: ComponentFixture<TaskListComponent>;
  let taskService: TaskService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TaskListComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), provideNoopAnimations()]
    }).compileComponents();
  });

  beforeEach(() => {
    // jsdom doesn't implement Element.scrollTo, which the CDK viewport calls to scroll the
    // highlighted row into view. Stub it so the scroll path is exercised rather than throwing.
    Element.prototype.scrollTo ??= (() => {}) as typeof Element.prototype.scrollTo;

    fixture = TestBed.createComponent(TaskListComponent);
    component = fixture.componentInstance;
    taskService = TestBed.inject(TaskService);
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('project scope', () => {
    const emptyPage = { count: 0, next: null, previous: null, results: [] };

    beforeEach(() => {
      vi.spyOn(taskService, 'getTasksPage').mockReturnValue(of(emptyPage));
      fixture.componentRef.setInput('project', 4);
      fixture.detectChanges();
    });

    it('narrows the query to the project it is scoped to', () => {
      expect(taskService.getTasksPage).toHaveBeenCalledWith(
        expect.objectContaining({ project: 4 }), 0, expect.any(Number),
      );
    });

    it('adds a quick-added task to that project', () => {
      const addTask = vi.spyOn(taskService, 'addTask').mockReturnValue(of(makeTask(9)));

      component.onQuickAdd({ title: 'Fix the nav', tags: [] });

      expect(addTask).toHaveBeenCalledWith(expect.objectContaining({ title: 'Fix the nav', project: 4 }));
    });

    it('drops the project chip from the rows — the whole list is that project', () => {
      expect(component.projectName(makeTask(1, { project: 4 }))).toBe('');
    });

    it('lets an explicit @project token win over the scope', () => {
      const addTask = vi.spyOn(taskService, 'addTask').mockReturnValue(of(makeTask(9)));

      component.onQuickAdd({ title: 'Fix the nav', tags: [], project: 7 });

      expect(addTask).toHaveBeenCalledWith(expect.objectContaining({ project: 7 }));
    });

    it('leaves the project off the query when the list is not scoped', () => {
      fixture.componentRef.setInput('project', null);
      fixture.detectChanges();

      expect(taskService.getTasksPage).toHaveBeenLastCalledWith(
        expect.objectContaining({ project: null }), 0, expect.any(Number),
      );
      const filters = vi.mocked(taskService.getTasksPage).mock.lastCall![0]!;
      expect(filters.getQueryString()).not.toContain('project=');
    });
  });

  describe('keyboard shortcuts', () => {
    let tasks: Task[];

    /** Swap in a data source backed by an in-memory page, so the highlight resolves to real tasks. */
    function seed(list: Task[]): void {
      tasks = list;
      const source = new TaskDataSource(() => of({ count: list.length, next: null, previous: null, results: list }));
      source.connect({ viewChange: new Subject() } as unknown as CollectionViewer).subscribe();
      component.dataSource.set(source);
      component.totalCount.set(list.length);
      fixture.detectChanges();
    }

    beforeEach(() => {
      vi.spyOn(taskService, 'updateTask').mockReturnValue(of(makeTask(1)));
      vi.spyOn(taskService, 'deleteTask').mockReturnValue(of(makeTask(1)));
      seed([makeTask(1), makeTask(2), makeTask(3)]);
    });

    it('moves the highlight with the arrow keys and clamps at both ends', () => {
      expect(component.highlighted()).toBe(-1);

      press('ArrowDown');
      expect(component.highlighted()).toBe(0);
      press('ArrowDown');
      expect(component.highlighted()).toBe(1);
      press('ArrowUp');
      expect(component.highlighted()).toBe(0);

      press('ArrowUp');
      expect(component.highlighted()).toBe(0);

      press('ArrowDown');
      press('ArrowDown');
      press('ArrowDown');
      expect(component.highlighted()).toBe(2);
    });

    it('toggles done on the highlighted task with Enter', () => {
      press('ArrowDown');
      press('Enter');

      expect(taskService.updateTask).toHaveBeenCalledWith(expect.objectContaining({ id: 1, completed: true }));
    });

    it('toggles today on the highlighted task with t', () => {
      press('ArrowDown');
      press('ArrowDown');
      press('t');

      expect(taskService.updateTask).toHaveBeenCalledWith(expect.objectContaining({ id: 2, for_today: true }));
    });

    it('deletes the highlighted task with Delete', () => {
      press('ArrowDown');
      press('Delete');

      expect(taskService.deleteTask).toHaveBeenCalledWith(1);
      expect(component.totalCount()).toBe(2);
    });

    it('opens the highlighted task for editing with e', () => {
      const router = TestBed.inject(Router);
      const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);

      press('ArrowDown');
      press('e');

      expect(navigate).toHaveBeenCalledWith(['/tasks', 1]);
    });

    it('does nothing when no task is highlighted', () => {
      press('Enter');
      press('t');
      press('Delete');

      expect(taskService.updateTask).not.toHaveBeenCalled();
      expect(taskService.deleteTask).not.toHaveBeenCalled();
    });

    it('keeps the highlight in bounds after deleting the last task', () => {
      press('ArrowDown');
      press('ArrowDown');
      press('ArrowDown');
      expect(component.highlighted()).toBe(2);

      press('Delete');
      fixture.detectChanges(); // flush the clamping effect
      expect(component.highlighted()).toBe(1);
    });

    it('focuses search on / and quick-add on c', () => {
      const search = fixture.nativeElement.querySelector('input[type="search"]') as HTMLInputElement;
      const quickAdd = fixture.nativeElement.querySelector('app-task-quick-add input') as HTMLInputElement;

      press('/');
      expect(document.activeElement).toBe(search);

      // Blur first: while focus is in a field, single-letter shortcuts are inert by design.
      search.blur();
      press('c');
      expect(document.activeElement).toBe(quickAdd);
    });

    it('toggles the filters with Ctrl+1/2/3', () => {
      expect(component.filters()).toEqual({ today: false, completed: false, todo: true });

      press('1', { ctrlKey: true });
      expect(component.filters()['todo']).toBe(false);

      press('2', { ctrlKey: true });
      expect(component.filters()['completed']).toBe(true);

      press('3', { ctrlKey: true });
      expect(component.filters()['today']).toBe(true);
    });

    it('opens the shortcuts panel with ? and closes it with Escape', () => {
      press('?');
      fixture.detectChanges();
      expect(component.shortcutsOpen()).toBe(true);
      expect(fixture.nativeElement.querySelector('.ks-panel')).toBeTruthy();

      press('Escape');
      fixture.detectChanges();
      expect(component.shortcutsOpen()).toBe(false);
      expect(fixture.nativeElement.querySelector('.ks-panel')).toBeFalsy();
    });

    it('ignores task shortcuts while the panel is open', () => {
      press('ArrowDown');
      press('?');
      press('ArrowDown');

      expect(component.highlighted()).toBe(0);
    });

    // Every bare key the list binds. None of these may fire while the user is typing, or the
    // character is swallowed instead of reaching the field.
    const BARE_KEYS = ['e', 't', 'c', '/', '?', 'Enter', 'Delete', 'ArrowDown', 'ArrowUp'];

    /** Focus a field, fire every bare shortcut at it, and assert none of them did anything. */
    function expectInert(field: HTMLElement, label: string): void {
      field.focus();
      press('ArrowDown'); // highlight something, so the row actions have a target to act on
      const highlightBefore = component.highlighted();

      for (const key of BARE_KEYS) press(key, {}, field);

      expect(taskService.updateTask, `${label}: updateTask`).not.toHaveBeenCalled();
      expect(taskService.deleteTask, `${label}: deleteTask`).not.toHaveBeenCalled();
      expect(component.shortcutsOpen(), `${label}: panel`).toBe(false);
      expect(component.highlighted(), `${label}: highlight`).toBe(highlightBefore);
      expect(document.activeElement, `${label}: focus`).toBe(field);
      expect(tasks[0].completed, `${label}: task untouched`).toBe(false);
    }

    it('does not hijack any bare key typed into the search field', () => {
      expectInert(fixture.nativeElement.querySelector('input[type="search"]'), 'search');
    });

    it('does not hijack any bare key typed into the quick-add field', () => {
      expectInert(fixture.nativeElement.querySelector('app-task-quick-add input'), 'quick-add');
    });

    it('does not hijack bare keys in a textarea or a contenteditable', () => {
      const textarea = document.createElement('textarea');
      const editable = document.createElement('div');
      editable.setAttribute('contenteditable', 'true');
      // A caret inside a child of the editable region still counts as typing.
      const child = document.createElement('span');
      editable.appendChild(child);
      fixture.nativeElement.append(textarea, editable);

      expectInert(textarea, 'textarea');
      vi.clearAllMocks();
      press('ArrowDown');
      const highlight = component.highlighted();
      for (const key of BARE_KEYS) press(key, {}, child);
      expect(taskService.updateTask).not.toHaveBeenCalled();
      expect(component.highlighted()).toBe(highlight);
      expect(component.shortcutsOpen()).toBe(false);
    });

    it('still runs the Ctrl shortcuts while typing', () => {
      const search = fixture.nativeElement.querySelector('input[type="search"]') as HTMLInputElement;
      search.focus();

      press('1', { ctrlKey: true }, search);

      expect(component.filters()['todo']).toBe(false);
      expect(document.activeElement).toBe(search);
    });

    it('resumes shortcuts once the field is left with Escape', () => {
      const search = fixture.nativeElement.querySelector('input[type="search"]') as HTMLInputElement;
      search.focus();
      press('Escape', {}, search);
      expect(document.activeElement).not.toBe(search);

      press('ArrowDown');
      expect(component.highlighted()).toBe(0);
    });

    it('ignores bare keys while the app-wide create-task drawer is open', () => {
      TestBed.inject(TaskDrawerService).open.set(true);
      press('ArrowDown');

      expect(component.highlighted()).toBe(-1);
      expect(taskService.updateTask).not.toHaveBeenCalled();
    });
  });
});
