import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Task } from './task';
import { MessageService } from '../message.service';
import {Observable, of} from 'rxjs';
import {catchError, map, switchMap, tap} from 'rxjs/operators';
import {TagService} from '../tags/tag.service';
import {Tag} from '../tags/tag';
import {query} from '@angular/animations';
import {coerceBooleanProperty} from '@angular/cdk/coercion';
import {TaskFilters} from './task-filters';
import {ServiceBase} from '../service-base';
import {environment} from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class TaskService extends ServiceBase {
  private tasksURL = `${environment.apiBase}/api/task/`

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


  getTasks(filters: TaskFilters | null = null): Observable<Task[]> {
    if (!filters) filters = new TaskFilters()
    let url = filters.getFilteredURL(this.tasksURL);
    return this.http.get<Task[]>(url)
      .pipe(
        tap((tasks: Task[]) => tasks.map((task: Task) => {
          this.processTagsFromServer(task);
          return task;
        })),
        tap(_ => this.log(`fetched ${_.length} tasks`)),
        catchError(this.handleError<Task[]>('getTasks', [])),
      )
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
}
