import { ChangeDetectionStrategy, Component, OnInit, signal } from '@angular/core';
import { NgClass } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Modal } from 'bootstrap';
import { forkJoin } from 'rxjs';
import { Task } from '../task';
import { TaskService } from '../task.service';
import { TagService } from '../../tags/tag.service';
import { Tag } from '../../tags/tag';
import { MarkdownComponent } from '../../shared/markdown/markdown.component';
import { TagChipsInputComponent } from '../../shared/tag-chips-input/tag-chips-input.component';
import { ProjectPickerComponent } from '../../shared/project-picker/project-picker.component';

@Component({
  selector: 'app-task-detail',
  imports: [FormsModule, NgClass, RouterLink, MarkdownComponent, TagChipsInputComponent, ProjectPickerComponent],
  templateUrl: './task-detail.component.html',
  styleUrls: ['./task-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskDetailComponent implements OnInit {
  readonly task = signal<Task | undefined>(undefined);
  readonly saving = signal(false);
  readonly previewOnly = signal(false);

  readonly statuses = [
    { value: 'idea', label: 'Idea' },
    { value: 'blocked', label: 'Blocked' },
    { value: 'inprogress', label: 'In progress' },
    { value: 'givenup', label: 'Given up' },
  ];
  readonly priorities = [
    { value: 4, label: 'High' },
    { value: 2, label: 'Normal' },
    { value: 1, label: 'Low' },
  ];

  private deleteModal?: Modal;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private taskService: TaskService,
    private tagService: TagService,
  ) { }

  ngOnInit(): void {
    const element = document.getElementById('deleteModal');
    if (element) {
      this.deleteModal = new Modal(element);
    }
    this.getTask();
  }

  getTask(): void {
    const id = parseInt(this.route.snapshot.paramMap.get('id')!, 10);
    // Resolve the task's tags from the full tag list so the chips (and a subsequent save) are
    // reliable — not dependent on the async per-id cache that could leave `_tags` undefined.
    forkJoin({ task: this.taskService.getTask(id), tags: this.tagService.getTagsCached() })
      .subscribe(({ task, tags }) => {
        const byId = new Map(tags.map((t) => [t.id, t]));
        task._tags = (task.tags ?? []).map((tid) => byId.get(tid)).filter((t): t is Tag => !!t);
        this.task.set(task);
      });
  }

  save(): void {
    const task = this.task();
    if (!task) return;
    this.saving.set(true);
    this.taskService.updateTask(task).subscribe({
      next: (updated) => {
        this.task.set(updated);
        this.saving.set(false);
      },
      error: () => this.saving.set(false),
    });
  }

  toggleCompleted(): void {
    const task = this.task();
    if (!task) return;
    task.completed = !task.completed;
    if (task.completed && task.for_today) task.for_today = false;
    this.save();
  }

  deleteTask(): void {
    const task = this.task();
    if (task?.id != null) {
      this.taskService.deleteTask(task.id).subscribe(() => this.router.navigate(['tasks']));
    }
  }

  /** ISO/Date value → `yyyy-MM-ddThh:mm` for `<input type="datetime-local">`. */
  dateForInput(value?: string | Date | null): string {
    if (!value) return '';
    const d = new Date(value);
    if (isNaN(d.getTime())) return '';
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  onDateChange(field: 'start_date' | 'end_date', event: Event): void {
    const task = this.task();
    if (!task) return;
    const value = (event.target as HTMLInputElement).value;
    (task as unknown as Record<string, unknown>)[field] = value ? new Date(value).toISOString() : undefined;
  }
}
