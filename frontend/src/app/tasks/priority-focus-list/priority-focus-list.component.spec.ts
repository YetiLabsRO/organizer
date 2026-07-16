import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { PriorityFocusListComponent } from './priority-focus-list.component';

describe('PriorityFocusListComponent', () => {
  let component: PriorityFocusListComponent;
  let fixture: ComponentFixture<PriorityFocusListComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PriorityFocusListComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), provideNoopAnimations()],
    }).compileComponents();
  });

  beforeEach(() => {
    fixture = TestBed.createComponent(PriorityFocusListComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  /** Answer the focus-counts request with `counts`; the list stays windowed at `rows`. */
  const respond = (counts: Partial<Record<string, number>>, rows: unknown[] = []) => {
    http.expectOne((r) => r.url.includes('/api/task/focus-counts/')).flush({
      total: 0, overdue: 0, high: 0, normal: 0, low: 0, due_today: 0, ...counts,
    });
    http.match((r) => r.url.includes('/api/task/') && !r.url.includes('focus-counts'))
      .forEach((r) => r.flush({ count: counts['total'] ?? 0, next: null, previous: null, results: rows }));
    fixture.detectChanges();
  };

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('renders the four priority bands', () => {
    const titles = Array.from(fixture.nativeElement.querySelectorAll('.band-title')).map(
      (el) => (el as HTMLElement).textContent?.trim(),
    );
    expect(titles).toEqual(['Urgent & Overdue', 'High Priority', 'Normal', 'Low Priority']);
  });

  it('starts on the Todo view', () => {
    expect(component.viewMode()).toBe('todo');
  });

  it('takes its tile counts from the server, not the fetched window', () => {
    // The window holds no overdue rows, but the server says the full set has 7. The tiles must
    // report the server's number — this is the under-count the endpoint exists to fix.
    respond({ total: 1202, overdue: 7, high: 3, due_today: 5 }, []);

    expect(component.overdueCount()).toBe(7);
    expect(component.highCount()).toBe(3);
    expect(component.dueTodayCount()).toBe(5);

    const tiles = Array.from(fixture.nativeElement.querySelectorAll('.stat-value')).map(
      (el) => (el as HTMLElement).textContent?.trim(),
    );
    expect(tiles).toEqual(['7', '3', '5']);
  });

  it('takes its band header counts from the server too', () => {
    respond({ total: 1202, overdue: 1, high: 0, normal: 1198, low: 3 }, []);

    expect(component.countIn('normal')).toBe(1198);
    expect(component.countIn('urgent')).toBe(1);
  });

  it('points at the full task list once the set outgrows the rendered window', () => {
    respond({ total: 1202, normal: 1198, overdue: 1, low: 3 }, []);

    expect(component.hasMore()).toBe(true);
    const more: HTMLElement = fixture.nativeElement.querySelector('.focus-more');
    expect(more.textContent).toContain(`Showing the first ${component.fetchLimit} of 1202 tasks`);
    expect(more.querySelector('a')?.getAttribute('href')).toBe('/tasks');
  });

  it('stays quiet when the whole set already fits in the window', () => {
    respond({ total: 3, normal: 3 }, [{ id: 1, title: 'a', priority: 2, tags: [] }]);

    expect(component.hasMore()).toBe(false);
    expect(fixture.nativeElement.querySelector('.focus-more')).toBeNull();
  });

  it('does not shout "more tasks" at an empty view', () => {
    respond({ total: 0 }, []);

    expect(fixture.nativeElement.querySelector('.focus-more')).toBeNull();
    expect(fixture.nativeElement.querySelector('.focus-empty')).not.toBeNull();
  });
});
