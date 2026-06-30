import { ChangeDetectionStrategy, Component, Input, OnInit, signal } from '@angular/core';
import { NgClass, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TaskService } from '../task.service';
import { Task } from '../task';
import { TagService } from '../../tags/tag.service';
import { Tag } from '../../tags/tag';
import { TagColorPipe } from '../../tags/tag-color.pipe';
import { forkJoin, Observable } from 'rxjs';
import { TaskFilters } from '../task-filters';
import { map } from 'rxjs/operators';

@Component({
  selector: 'app-task-list',
  imports: [FormsModule, NgClass, DatePipe, RouterLink, TagColorPipe],
  templateUrl: './task-list.component.html',
  styleUrls: ['./task-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskListComponent implements OnInit {
  readonly tasks = signal<Task[]>([]);
  readonly tags = signal<Tag[]>([]);
  readonly activeTaskCount = signal(0);
  readonly filters = signal<{ [k: string]: boolean }>({});

  selectedTask?: Task;
  taskInput = '';

  @Input() filters_tags: Tag[] | null = null;
  @Input() for_tag: Tag | null = null;

  constructor(
    private taskService: TaskService,
    private tagService: TagService
  ) { }

  ngOnInit(): void {
    this.getTags();

    this.filters.set({
      'today': false,
      'completed': false,
      'todo': true,
    });
    this.getTasks();
  }

  toggleFilters(filter: string): void {
    const current = this.filters();
    if (!(filter in current)) return;
    this.filters.set({ ...current, [filter]: !current[filter] });
    this.getTasks();
  }

  processFilters(useCompletedDate: boolean = false): TaskFilters {
    const filters = this.filters();
    let completed: boolean | null = null;
    if (filters['completed'] != filters['todo']) {
      completed = filters['completed'];
    }

    let forToday: boolean | null = filters['today'] ? true : null;

    let tags: Tag[] | null = this.filters_tags || null;

    let completed_date: Date | null = null;
    if (useCompletedDate) {
      completed_date = new Date();
      //  completed date task-list have forToday disabled
      forToday = null;
    }

    return new TaskFilters(completed, null, completed_date, tags, forToday);
  }

  getTasks(): void {
    const filters = this.filters();
    let tasks$: Observable<Task[]>;
    if (filters['today'] && filters['completed']) {
      //  have to do 2 calls to the API
      let filtersNoDate = this.processFilters(false);
      let filtersDate = this.processFilters(true);
      tasks$ = forkJoin([this.taskService.getTasks(filtersNoDate),
        this.taskService.getTasks(filtersDate)]).pipe(
          map((taskResponses: [Task[], Task[]]) => [...taskResponses[0], ...taskResponses[1]])
      );
    } else {
      let f = this.processFilters();
      tasks$ = this.taskService.getTasks(f);
    }

    tasks$
      .subscribe(tasks => {
        this.tasks.set(tasks);
        this.activeTaskCount.set(tasks.reduce((count, task) => count + (task.completed ? 0 : 1), 0));
      });
  }

  getTags(): void {
    this.tagService.getTags()
      .subscribe(tags => this.tags.set(tags));
  }

  onSelect(task: Task): void {
    this.selectedTask = task;
  }

  addTask(taskDescription: string): void {
    let tag_re = /^(?<title>.+?)(@tags\((?<tags>[\w ,-]+)\))?$/ui;
    let matches = taskDescription.match(tag_re);

    let tags: string | undefined = matches?.groups?.tags;
    let title: string | undefined = matches?.groups?.title;

    if (!title) {
      return;
    }

    let task: Task = {
      title: title,
      for_today: this.filters()['today'],
      tags: [],
      _tags: []
    };

    if (tags === undefined) {
      this.taskService.addTask(task as Task).subscribe((task: Task) => this.tasks.update(t => [...t, task]));
      this.taskInput = '';
      return;
    }

    let parsed_tags: string[] = tags.split(/\s*(?:,|$)\s*/);
    let tags$: Observable<Tag[]>[] = [];

    // have to resolve tags-list to IDs
    parsed_tags.forEach((tag: string) => tags$.push(this.tagService.getTagBySlug(tag)));
    forkJoin(tags$).subscribe((res_tags: Tag[][]) => {
      res_tags.forEach((tags: Tag[]) => {
        if (tags.length) {
          task.tags.push(tags[0].id);
          task._tags.push(tags[0]);
        }
      });
      this.taskService.addTask(task as Task).subscribe((task: Task) => this.tasks.update(t => [task, ...t]));
    });

    this.taskInput = '';
  }

  deleteTask(task: Task): void {
    if (task.id != null) {
      this.taskService.deleteTask(task.id).subscribe();
    }
    this.tasks.update(tasks => tasks.filter(t => t.id !== task.id));
  }

  toggleTaskDone(task: Task): void {
    if (!task) return;
    this.activeTaskCount.update(count => count + (task.completed ? 1 : -1));
    task.completed = !task.completed;
    if (task.completed && task.for_today) task.for_today = false;
    this.taskService.updateTask(task).subscribe();

    const filters = this.filters();
    if ((!filters['completed'] && filters['todo']) ||
      (!filters['todo'] && filters['completed'])) {
      this.tasks.update(tasks => tasks.filter((t: Task) => filters['todo'] ? !t.completed : t.completed));
    } else {
      this.tasks.update(tasks => [...tasks]);
    }
  }

  toggleTaskToday(task: Task): void {
    if (!task || task.completed) return;
    task.for_today = !task.for_today;
    this.taskService.updateTask(task).subscribe();
    if (this.filters()['today']) {
      this.tasks.update(tasks => tasks.filter((t: Task) => t.for_today));
    } else {
      this.tasks.update(tasks => [...tasks]);
    }
  }
}
