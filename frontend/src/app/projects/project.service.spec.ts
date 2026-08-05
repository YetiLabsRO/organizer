import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { ProjectService } from './project.service';
import { Project } from './project';

describe('ProjectService', () => {
  let instance: ProjectService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [ProjectService, provideHttpClient(), provideHttpClientTesting(), provideRouter([])]
    });
    instance = TestBed.inject(ProjectService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('should be created', () => {
    expect(instance).toBeTruthy();
  });

  it('emits a project that has no tags (it used to never emit, leaving the detail view blank)', () => {
    const seen: (Project | null)[] = [];
    instance.getProject(4).subscribe((project) => seen.push(project));

    http.expectOne((req) => req.url.endsWith('/api/project/4/'))
      .flush({ id: 4, title: 'Website', slug: 'website', tags: [] });

    expect(seen.length).toBe(1);
    expect(seen[0]?.title).toBe('Website');
    expect(seen[0]?._tags).toEqual([]);
  });

  it('does not hand the previously viewed project to the next detail view', () => {
    instance.getProject(4).subscribe();
    http.expectOne((req) => req.url.endsWith('/api/project/4/'))
      .flush({ id: 4, title: 'Website', slug: 'website', tags: [] });

    const seen: (Project | null)[] = [];
    instance.getProject(5).subscribe((project) => seen.push(project));

    // Nothing yet — the previous project must not leak through while #5 is in flight.
    expect(seen).toEqual([]);

    http.expectOne((req) => req.url.endsWith('/api/project/5/'))
      .flush({ id: 5, title: 'Garden', slug: 'garden', tags: [] });

    expect(seen.map((p) => p?.id)).toEqual([5]);
  });
});
