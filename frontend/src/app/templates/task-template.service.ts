import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';

import { ServiceBase } from '../service-base';
import { MessageService } from '../message.service';
import { TagService } from '../tags/tag.service';
import { Tag } from '../tags/tag';
import { environment } from '../../environments/environment';
import { TaskTemplate } from './task-template';

@Injectable({
  providedIn: 'root',
})
export class TaskTemplateService extends ServiceBase {
  private readonly http = inject(HttpClient);
  private readonly tagService = inject(TagService);

  private readonly templatesURL = `${environment.apiBase}/api/template/`;

  private readonly httpOptions = {
    headers: new HttpHeaders({ 'Content-Type': 'application/json' }),
  };

  constructor() {
    super(inject(MessageService));
  }

  private detailURL(id: number | string): string {
    return `${this.templatesURL}${id}/`;
  }

  /** Map the `_tags` chip objects onto the `tags` id array the API expects. */
  private processTagsToServer(template: TaskTemplate): void {
    template.tags = (template._tags ?? []).map((tag) => tag.id).filter((id): id is number => id != null);
  }

  /** Hydrate `_tags` from the `tags` id array for display. */
  private hydrateTags(template: TaskTemplate): void {
    if (template.tags?.length) {
      this.tagService.getTagsByID(template.tags).subscribe((tags: Tag[]) => (template._tags = tags));
    } else {
      template._tags = [];
    }
  }

  getTemplates(): Observable<TaskTemplate[]> {
    return this.http.get<TaskTemplate[]>(this.templatesURL).pipe(
      tap((templates) => templates.forEach((t) => this.hydrateTags(t))),
      tap((templates) => this.log(`fetched ${templates.length} templates`)),
      catchError(this.handleError<TaskTemplate[]>('getTemplates', [])),
    );
  }

  getTemplate(id: number | string): Observable<TaskTemplate> {
    return this.http.get<TaskTemplate>(this.detailURL(id)).pipe(
      tap((template) => this.hydrateTags(template)),
      catchError(this.handleError<TaskTemplate>('getTemplate')),
    );
  }

  createTemplate(template: TaskTemplate): Observable<TaskTemplate> {
    this.processTagsToServer(template);
    return this.http.post<TaskTemplate>(this.templatesURL, template, this.httpOptions).pipe(
      tap((created) => this.log(`created template id=${created.id}`)),
      catchError(this.handleError<TaskTemplate>('createTemplate')),
    );
  }

  updateTemplate(template: TaskTemplate): Observable<TaskTemplate> {
    this.processTagsToServer(template);
    return this.http.put<TaskTemplate>(this.detailURL(template.id ?? 0), template, this.httpOptions).pipe(
      tap((updated) => this.log(`updated template id=${updated.id}`)),
      catchError(this.handleError<TaskTemplate>('updateTemplate')),
    );
  }

  deleteTemplate(id: number): Observable<unknown> {
    return this.http.delete(this.detailURL(id), this.httpOptions).pipe(
      tap(() => this.log(`deleted template ${id}`)),
      catchError(this.handleError('deleteTemplate')),
    );
  }

  /** Generate the currently-due task immediately (overrides skip-if-previous-open server-side). */
  runTemplate(id: number): Observable<unknown> {
    return this.http.post(`${this.detailURL(id)}run/`, {}, this.httpOptions).pipe(
      tap(() => this.log(`ran template ${id}`)),
      catchError(this.handleError('runTemplate')),
    );
  }
}
