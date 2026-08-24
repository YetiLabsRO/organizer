import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { NotionService } from './notion.service';
import { NotionConnection } from './notion.model';

describe('NotionService', () => {
  let instance: NotionService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [NotionService, provideHttpClient(), provideHttpClientTesting()],
    });
    instance = TestBed.inject(NotionService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('should be created', () => {
    expect(instance).toBeTruthy();
  });

  it('reports a disconnected account without inventing a status', () => {
    let seen: NotionConnection | undefined;
    instance.status().subscribe((state) => (seen = state));

    http.expectOne((req) => req.url.endsWith('/api/integrations/notion/status/'))
      .flush({ connected: false, configured: true });

    expect(seen?.connected).toBe(false);
    expect(seen?.status).toBeUndefined();
  });

  it('asks the server for an authorize URL rather than building one client-side', () => {
    // The URL carries a single-use `state` the server minted; the SPA must never construct it.
    let url = '';
    instance.connect().subscribe((response) => (url = response.authorize_url));

    const request = http.expectOne((req) => req.url.endsWith('/api/integrations/notion/connect/'));
    expect(request.request.method).toBe('POST');
    request.flush({ authorize_url: 'https://api.notion.com/v1/oauth/authorize?state=abc&owner=user' });

    expect(url).toContain('owner=user');
  });

  it('sends the chosen parent page when provisioning', () => {
    instance.provision('page-123').subscribe();

    const request = http.expectOne((req) => req.url.endsWith('/api/integrations/notion/provision/'));
    expect(request.request.body).toEqual({ parent_page_id: 'page-123' });
    request.flush({ connected: true, configured: true, provisioned: true });
  });

  it('passes the full-sync flag through', () => {
    instance.sync(true).subscribe();

    const request = http.expectOne((req) => req.url.endsWith('/api/integrations/notion/sync/'));
    expect(request.request.body).toEqual({ full: true });
    request.flush({ queued: true });
  });

  it('defaults a sync to incremental', () => {
    instance.sync().subscribe();

    const request = http.expectOne((req) => req.url.endsWith('/api/integrations/notion/sync/'));
    expect(request.request.body).toEqual({ full: false });
    request.flush({ queued: true });
  });
});
