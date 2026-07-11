import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Task, TaskComment } from './task';
import { MessageService } from '../message.service';
import {Observable} from 'rxjs';
import {catchError, tap} from 'rxjs/operators';
import {TagService} from '../tags/tag.service';
import {Tag} from '../tags/tag';
import {TaskFilters} from './task-filters';
import {ServiceBase} from '../service-base';
import {environment} from '../../environments/environment';
import {Page} from '../page';

@Injectable({
  providedIn: 'root'
})
export class TaskService extends ServiceBase {
  private tasksURL = `${environment.apiBase}/api/task/`
  private commentsURL = `${environment.apiBase}/api/comments/`

  httpOptions = {
    headers: new HttpHeaders({'Content-Type': 'application/json'})
  }

  constructor(
    private http: HttpClient,
    protected override messageService: MessageService,
    private tagService: TagService) {
    super(messageService);
  }

  processTagsFromServer(task: Task) {
    if (task.tags.length) {
      this.tagService.getTagsByID(task.tags).subscribe((tags: Tag[]) => {
        task._tags = tags
      });
    }
  }


  processTagsToServer(task: Task): void {
    task.tags = [];
    if (task._tags) {
      task.tags = task._tags.map(tag => tag.id)
    }
  }


  /**
   * Fetch one window of tasks from the paginated API.
   * `offset`/`limit` map onto the virtual-scroll range; the response is the
   * DRF `{count, next, previous, results}` envelope.
   */
  getTasksPage(filters: TaskFilters | null, offset: number, limit: number): Observable<Page<Task>> {
    if (!filters) filters = new TaskFilters();
    const base = filters.getFilteredURL(this.tasksURL);
    const sep = base.includes('?') ? '&' : '?';
    const url = `${base}${sep}limit=${limit}&offset=${offset}`;
    return this.http.get<Page<Task>>(url)
      .pipe(
        tap((page: Page<Task>) => page.results.forEach((task: Task) => this.processTagsFromServer(task))),
        tap((page: Page<Task>) => this.log(`fetched ${page.results.length}/${page.count} tasks @${offset}`)),
        catchError(this.handleError<Page<Task>>('getTasksPage')),
      );
  }

  getTagsForTask(task: Task) {
    if (!task.tags) {
      task.tags = [];
    }

    return this.tagService.getTagsByID(task.tags);
  }

  getTask(id: number): Observable<Task> {
    const url = `${this.tasksURL}${id}`
    return this.http.get<Task>(url)
      .pipe(
        tap((task: Task) => { this.processTagsFromServer(task)} ),
        tap(_ => this.log(`fetched task ${id}`)),
        catchError(this.handleError<Task>('getTask'))
      );
  }

  addTask(task: Task): Observable<Task> {
    this.processTagsToServer(task);
    return this.http.post<Task>(this.tasksURL, task, this.httpOptions)
      .pipe(
        tap((newTask: Task) => this.log(`added task id=${newTask.id}`)),
        tap((task: Task) => { this.processTagsFromServer(task)}),
        catchError(this.handleError<Task>('save task'))
      );
  }

  deleteTask(id: number): Observable<Task> {
    const url = `${this.tasksURL}${id}/`;
    return this.http.delete<Task>(url, this.httpOptions)
      .pipe(
        tap(_ => this.log(`deleted task with ID ${id}`)),
        catchError(this.handleError<Task>('deleted task'))
      );
  }

  updateTask(task: Task): Observable<Task> {
    const url = `${this.tasksURL}${task.id}/`;
    this.processTagsToServer(task);

    return this.http.put<Task>(url, task, this.httpOptions)
      .pipe(
        tap((task: Task) => { this.processTagsFromServer(task) }),
        tap((updatedTask: Task) => this.log(`updated task id=${updatedTask.id}`)),
        catchError(this.handleError<Task>('update task'))
      );
  }

  /** Add a comment to a task. The author is set server-side from the authenticated user. */
  addComment(taskId: number, description: string): Observable<TaskComment> {
    const body: TaskComment = { task: taskId, description };
    return this.http.post<TaskComment>(this.commentsURL, body, this.httpOptions)
      .pipe(
        tap((comment: TaskComment) => this.log(`added comment id=${comment.id} on task ${taskId}`)),
        catchError(this.handleError<TaskComment>('add comment'))
      );
  }
}
