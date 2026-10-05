import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';

import { VolunHubSettingsComponent } from './volunhub-settings.component';
import { ProjectService } from '../../projects/project.service';

describe('VolunHubSettingsComponent', () => {
  let fixture: ComponentFixture<VolunHubSettingsComponent>;
  let http: HttpTestingController;
  const projects = [
    { id: 1, title: 'Jamboree (VolunHub)', slug: 'j', _tags: [], tags: [] },
    { id: 2, title: 'Jamboree', slug: 'jam', _tags: [], tags: [] },
  ];

  function setup(query: Record<string, string> = {}): void {
    TestBed.configureTestingModule({
      imports: [VolunHubSettingsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ActivatedRoute, useValue: { queryParamMap: of(convertToParamMap(query)) } },
        { provide: ProjectService, useValue: { getProjects: () => of(projects), invalidateProjectsCache: () => {} } },
      ],
    });
    fixture = TestBed.createComponent(VolunHubSettingsComponent);
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  }

  function flushStatus(body: Record<string, unknown>): void {
    http.expectOne((req) => req.url.endsWith('/volunhub/status/')).flush({ base_url: 'https://vh', configured: true, ...body });
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  afterEach(() => http.verify());

  it('offers to connect when not connected', () => {
    setup();
    flushStatus({ connected: false });
    expect(text()).toContain('Connect VolunHub');
    expect(text()).not.toContain('Disconnect VolunHub');
  });

  it('explains a read-only connection', () => {
    setup();
    flushStatus({ connected: true, status: 'active', can_write: false, content_push_enabled: true });
    http.expectOne((req) => req.url.endsWith('/volunhub/projects/')).flush([]);
    fixture.detectChanges();
    expect(text()).toContain('Read-only');
  });

  it('offers to retry when content push was disabled', () => {
    setup();
    flushStatus({ connected: true, status: 'active', can_write: true, content_push_enabled: false });
    http.expectOne((req) => req.url.endsWith('/volunhub/projects/')).flush([]);
    fixture.detectChanges();
    expect(text()).toContain('Only status changes are sent to VolunHub');
    expect(text()).toContain('Retry content sync');
  });

  it('reports the callback outcome from the query string', () => {
    setup({ volunhub: 'error', reason: 'insufficient_scope' });
    flushStatus({ connected: false });
    expect(text()).toContain('did not grant access to read your tasks');
  });

  it('merges a VolunHub project into the chosen local project', () => {
    setup();
    flushStatus({ connected: true, status: 'active', can_write: true, content_push_enabled: true });
    http.expectOne((req) => req.url.endsWith('/volunhub/projects/')).flush([
      { external_id: 7, external_name: 'Jamboree', external_slug: 'j', auto_created: true, project_id: 1, project_title: 'Jamboree (VolunHub)' },
    ]);
    fixture.detectChanges();

    const select = (fixture.nativeElement as HTMLElement).querySelector('table select') as HTMLSelectElement;
    select.value = '2';
    select.dispatchEvent(new Event('change'));

    const request = http.expectOne((req) => req.url.endsWith('/volunhub/projects/7/merge/'));
    expect(request.request.body).toEqual({ project_id: 2 });
    request.flush({ external_id: 7, external_name: 'Jamboree', external_slug: 'j', auto_created: false, project_id: 2, project_title: 'Jamboree' });
    fixture.detectChanges();
    expect(text()).toContain('now maps to "Jamboree"');
  });
});
