import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { VolunHubConnection, VolunHubProjectLink } from './volunhub.model';

/**
 * Client for the VolunHub integration endpoints.
 *
 * Like Notion, connecting is two steps: the server registers itself with VolunHub if needed and
 * hands back an authorize URL bound to a single-use `state` (and a PKCE verifier it keeps), then
 * the browser *navigates* there so the user can log in and approve.
 */
@Injectable({ providedIn: 'root' })
export class VolunHubService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiBase}/api/integrations/volunhub`;

  status(): Observable<VolunHubConnection> {
    return this.http.get<VolunHubConnection>(`${this.base}/status/`);
  }

  connect(): Observable<{ authorize_url: string }> {
    return this.http.post<{ authorize_url: string }>(`${this.base}/connect/`, {});
  }

  disconnect(): Observable<VolunHubConnection> {
    return this.http.post<VolunHubConnection>(`${this.base}/disconnect/`, {});
  }

  /** Queued server-side. `retryContent` re-enables content edits after VolunHub refused one. */
  sync(retryContent = false): Observable<{ queued: boolean }> {
    return this.http.post<{ queued: boolean }>(`${this.base}/sync/`, { retry_content: retryContent });
  }

  projects(): Observable<VolunHubProjectLink[]> {
    return this.http.get<VolunHubProjectLink[]>(`${this.base}/projects/`);
  }

  /** Map a VolunHub project onto an existing local project. */
  mergeProject(externalId: number, projectId: number): Observable<VolunHubProjectLink> {
    return this.http.post<VolunHubProjectLink>(`${this.base}/projects/${externalId}/merge/`, {
      project_id: projectId,
    });
  }
}
