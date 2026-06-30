import {Injectable} from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import {MessageService} from '../message.service';
import {TagService} from '../tags/tag.service';
import {BehaviorSubject, Observable, throwError} from 'rxjs';
import {Project} from './project';
import {catchError, filter, tap} from 'rxjs/operators';
import {ServiceBase} from '../service-base';
import {Tag} from '../tags/tag';
import {Task} from '../tasks/task';
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

  processTagsFromServer(project: Project): void {
    if (project.tags.length) {
      this.tagService.getTagsByID(project.tags).subscribe((tags: Tag[]) => {
        project._tags = tags;
        this.project.next(project);
      })
    } else {
      project._tags = []
    }
  }

  getProjects(): Observable<Project[]> {
    return this.http.get<Project[]>(this.projectsURL)
      .pipe(
        tap((projects: Project[]) => projects.map((project: Project) => {
          this.processTagsFromServer(project);
          return project;
        })),
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

  _getProject(projectId: number | string): void {
    const url = this.getDetailURL(projectId);
    this.http.get<Project>(url)
      .pipe(
        tap((project: Project) => {
          this.processTagsFromServer(project);
        }),
        tap(_ => this.log(`fetched project ${_.id}`)),
        catchError(error => {
          this.clearProject()
          return throwError(error);
        })
    ).pipe(
      catchError(this.handleError<Project>('getProject'))
    ).subscribe()
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
        tap((newProject: Project) => {
          this.processTagsFromServer(newProject);
        }),
        tap((newproject: Project) => this.log(`added project id=${newproject.id}`)),
        catchError(this.handleError<Project>('create Project'))
      )
  }

  updateProject(project: Project): Observable<Project> {
    const url = this.getDetailURL(project.id || 0);

    this.processTagsToServer(project);
    return this.http.put<Project>(url, project, this.httpOptions)
      .pipe(
        tap((updatedProject: Project) => {
          this.processTagsFromServer(updatedProject);
        }),
        tap((updatedProject: Project) => this.log(`updated project id=${updatedProject.id}`)),
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
