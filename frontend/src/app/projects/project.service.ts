import {Injectable} from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import {MessageService} from '../message.service';
import {TagService} from '../tags/tag.service';
import {BehaviorSubject, Observable, forkJoin, of} from 'rxjs';
import {Project} from './project';
import {catchError, filter, map, shareReplay, switchMap, tap} from 'rxjs/operators';
import {ServiceBase} from '../service-base';
import {Tag} from '../tags/tag';
import {environment} from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class ProjectService extends ServiceBase {
  private projectsURL = `${environment.apiBase}/api/project/`;
  project: BehaviorSubject<Project | null> = new BehaviorSubject<Project | null>(null);
  projectList: BehaviorSubject<Project[]> = new BehaviorSubject<Project[]>([]);

  httpOptions = {
    headers: new HttpHeaders({'Content-Type': 'application/json'})
  }

  constructor(
    private http: HttpClient,
    protected override messageService: MessageService,
    private tagService: TagService) {
    super(messageService);
  }

  processTagsToServer(project: Project): void {
    project.tags = [];
    if (project._tags) {
      project.tags = project._tags.map(tag => tag.id)
    }
  }

  /**
   * Resolve a project's tag ids onto `_tags`, emitting the project once they've landed.
   *
   * The project is only emitted *after* its tags resolve, so a consumer holding it in a signal
   * renders the pills without needing a second change-detection pass. A project with no tags
   * emits straight away — `forkJoin([])` completes without emitting, which is what used to leave
   * the detail view permanently blank for untagged projects.
   */
  processTagsFromServer(project: Project): Observable<Project> {
    project._tags = [];
    if (!project.tags?.length) {
      return of(project);
    }
    return this.tagService.getTagsByID(project.tags).pipe(
      map((tags: Tag[]) => {
        project._tags = tags;
        return project;
      }),
      catchError(() => of(project)),
    );
  }

  private projectsCache$?: Observable<Project[]>;

  /** Shared, cached full project list — used for `@project` autocomplete and id → title lookup. */
  getProjectsCached(): Observable<Project[]> {
    if (!this.projectsCache$) {
      this.projectsCache$ = this.getProjects().pipe(shareReplay(1));
    }
    return this.projectsCache$;
  }

  /** Drop the cached project list so the next autocomplete/lookup sees new or renamed projects. */
  invalidateProjectsCache(): void {
    this.projectsCache$ = undefined;
  }

  getProjects(): Observable<Project[]> {
    return this.http.get<Project[]>(this.projectsURL)
      .pipe(
        switchMap((projects: Project[]) =>
          projects.length ? forkJoin(projects.map(project => this.processTagsFromServer(project))) : of([])),
        tap(_ => this.log(`fetched ${_.length} projects`)),
        catchError(this.handleError<Project[]>('getProjects', []))
      )
  }

  getDetailURL(project_id: number | string): string {
    return `${this.projectsURL}${project_id}/`;
  }

  clearProject(): void {
    this.project.next(null);
  }

  getProject(projectId: number | string): Observable<Project | null> {
    this._getProject(projectId);
    return this.project.asObservable().pipe(
      filter(item => item !== null)
    )
  }

  /**
   * Fetch one project with its tags resolved. Unlike `getProject`, the returned observable is the
   * request itself — it completes, and errors reach the caller, so a view can tell "still loading"
   * from "no such project".
   */
  fetchProject(projectId: number | string): Observable<Project> {
    return this.http.get<Project>(this.getDetailURL(projectId))
      .pipe(
        switchMap((project: Project) => this.processTagsFromServer(project)),
        tap(_ => this.log(`fetched project ${_.id}`)),
      )
  }

  _getProject(projectId: number | string): void {
    // Drop whatever was last viewed first, so the subject can't hand the previous project to a
    // detail view that's waiting on this fetch.
    this.clearProject();
    this.fetchProject(projectId)
      .pipe(catchError(this.handleError<Project>('getProject')))
      .subscribe({
        next: (project: Project) => this.project.next(project),
        error: () => this.clearProject(),
      })
  }

  cleanFormValues(project: Project) {
    let nullableKeys: (keyof Project)[] = ["start_date", "end_date", "description"];
    nullableKeys.forEach(key => {
      if (project[key] === "") {
        //  project as any here to be able to programmatically set values to null
        (project as any)[key] = null;
      }
    });
  }

  createProject(project: Project): Observable<Project> {
    const url = this.projectsURL;

    this.processTagsToServer(project);
    this.cleanFormValues(project);
    return this.http.post<Project>(url, project, this.httpOptions)
      .pipe(
        switchMap((newProject: Project) => this.processTagsFromServer(newProject)),
        tap((newproject: Project) => this.log(`added project id=${newproject.id}`)),
        tap(() => this.invalidateProjectsCache()),
        catchError(this.handleError<Project>('create Project'))
      )
  }

  updateProject(project: Project): Observable<Project> {
    const url = this.getDetailURL(project.id || 0);

    this.processTagsToServer(project);
    this.cleanFormValues(project);
    return this.http.put<Project>(url, project, this.httpOptions)
      .pipe(
        switchMap((updatedProject: Project) => this.processTagsFromServer(updatedProject)),
        tap((updatedProject: Project) => this.log(`updated project id=${updatedProject.id}`)),
        tap((updatedProject: Project) => this.project.next(updatedProject)),
        tap(() => this.invalidateProjectsCache()),
        catchError(this.handleError<Project>('update Project'))
      )
  }

  deleteProject(project: Project): Observable<Project> {
    const url = this.getDetailURL(project.id || 0);
    return this.http.delete<Project>(url, this.httpOptions)
      .pipe(
        tap(_ => this.log(`deleted project ${_.id}`)),
        catchError(this.handleError<Project>('deleteProject'))
      )
  }
}
