import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { NotionConnection, NotionPage } from './notion.model';

/**
 * Client for the Notion integration endpoints.
 *
 * Connecting deliberately takes two steps: the server hands back an authorize URL bound to a
 * single-use `state`, and the browser then *navigates* to Notion. It cannot be an XHR — the user
 * has to see Notion's consent screen and pick which pages to share.
 */
@Injectable({ providedIn: 'root' })
export class NotionService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiBase}/api/integrations/notion`;

  status(): Observable<NotionConnection> {
    return this.http.get<NotionConnection>(`${this.base}/status/`);
  }

  connect(): Observable<{ authorize_url: string }> {
    return this.http.post<{ authorize_url: string }>(`${this.base}/connect/`, {});
  }

  disconnect(): Observable<NotionConnection> {
    return this.http.post<NotionConnection>(`${this.base}/disconnect/`, {});
  }

  /** Pages the user ticked on Notion's consent screen — the only places a database can go. */
  pages(): Observable<NotionPage[]> {
    return this.http.get<NotionPage[]>(`${this.base}/pages/`);
  }

  provision(parentPageId: string): Observable<NotionConnection> {
    return this.http.post<NotionConnection>(`${this.base}/provision/`, { parent_page_id: parentPageId });
  }

  /** Queued server-side; the response only confirms it was accepted. */
  sync(full = false): Observable<{ queued: boolean }> {
    return this.http.post<{ queued: boolean }>(`${this.base}/sync/`, { full });
  }
}
