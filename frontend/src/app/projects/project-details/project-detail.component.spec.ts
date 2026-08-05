import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of } from 'rxjs';

import { ProjectDetailComponent } from './project-detail.component';
import { TaskDrawerService } from '../../tasks/task-drawer.service';

describe('ProjectDetailComponent', () => {
  let component: ProjectDetailComponent;
  let fixture: ComponentFixture<ProjectDetailComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    // jsdom has no Element.scrollTo, which the embedded task list's CDK viewport calls.
    Element.prototype.scrollTo ??= (() => {}) as typeof Element.prototype.scrollTo;

    await TestBed.configureTestingModule({
      imports: [ProjectDetailComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: ActivatedRoute, useValue: { paramMap: of(convertToParamMap({ id: '4' })) } },
      ]
    }).compileComponents();
  });

  beforeEach(() => {
    fixture = TestBed.createComponent(ProjectDetailComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  /** Answer the project fetch the component fires on init. */
  function loadProject(body: Record<string, unknown> = {}): void {
    http.expectOne((req) => req.url.endsWith('/api/project/4/'))
      .flush({ id: 4, title: 'Website rebuild', slug: 'website-rebuild', tags: [], ...body });
    fixture.detectChanges();
  }

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('renders an untagged project and lists its tasks', () => {
    loadProject();

    expect(fixture.nativeElement.textContent).toContain('Website rebuild');
    expect(fixture.nativeElement.querySelector('app-task-list')).toBeTruthy();
    // The embedded list is scoped, so it only ever shows this project's tasks.
    const scoped = http.match((req) => req.url.includes('/api/task/') && req.url.includes('project=4'));
    expect(scoped.length).toBeGreaterThan(0);
  });

  it('New Task opens the shared drawer pre-filled with the project', () => {
    loadProject();
    const drawer = TestBed.inject(TaskDrawerService);

    component.newTask();

    expect(drawer.open()).toBe(true);
    expect(drawer.preset()).toEqual({ project: 4 });
  });

  it('shows a not-found message when the project does not exist', () => {
    http.expectOne((req) => req.url.endsWith('/api/project/4/'))
      .flush({ detail: 'Not found.' }, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();

    expect(component.notFound()).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('Project not found');
  });
});
