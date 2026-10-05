import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { VolunHubService } from './volunhub.service';
import { VolunHubConnection } from './volunhub.model';

describe('VolunHubService', () => {
  let instance: VolunHubService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [VolunHubService, provideHttpClient(), provideHttpClientTesting()],
    });
    instance = TestBed.inject(VolunHubService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('reports a disconnected account without inventing a status', () => {
    let seen: VolunHubConnection | undefined;
    instance.status().subscribe((state) => (seen = state));

    http
      .expectOne((req) => req.url.endsWith('/api/integrations/volunhub/status/'))
      .flush({ connected: false, configured: true, base_url: 'https://volunhub.scout.ro' });

    expect(seen?.connected).toBe(false);
    expect(seen?.status).toBeUndefined();
  });

  it('asks the server for the authorize URL rather than building one client-side', () => {
    let url = '';
    instance.connect().subscribe((response) => (url = response.authorize_url));

    const request = http.expectOne((req) => req.url.endsWith('/api/integrations/volunhub/connect/'));
    expect(request.request.method).toBe('POST');
    request.flush({ authorize_url: 'https://volunhub.scout.ro/authorize?state=abc&code_challenge=x' });

    expect(url).toContain('code_challenge=');
  });

  it('sends retry_content when re-enabling content edits', () => {
    instance.sync(true).subscribe();

    const request = http.expectOne((req) => req.url.endsWith('/api/integrations/volunhub/sync/'));
    expect(request.request.body).toEqual({ retry_content: true });
    request.flush({ queued: true });
  });

  it('merges a project by external id', () => {
    instance.mergeProject(7, 42).subscribe();

    const request = http.expectOne((req) => req.url.endsWith('/api/integrations/volunhub/projects/7/merge/'));
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ project_id: 42 });
    request.flush({ external_id: 7, project_id: 42 });
  });
});
