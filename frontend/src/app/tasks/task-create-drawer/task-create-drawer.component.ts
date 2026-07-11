import { ChangeDetectionStrategy, Component, effect, inject, model, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { Task } from '../task';
import { TaskService } from '../task.service';
import { Tag } from '../../tags/tag';
import { TagChipsInputComponent } from '../../shared/tag-chips-input/tag-chips-input.component';
import { ProjectPickerComponent } from '../../shared/project-picker/project-picker.component';

interface Draft {
  title: string;
  priority: number;
  end_date?: string; // ISO string bound to <input type="datetime-local">
  estimated_time?: number;
  description: string;
  for_today: boolean;
  project?: number;
  tags: Tag[];
}

/**
 * Slide-in "Create New Task" drawer (right panel + scrim), from the Figma redesign.
 * Covers the fields the app actually models — title, priority, deadline, estimate, project,
 * tags, description, focus-today — reusing the shared tag/project pickers. The mockup's
 * provider/repo fields are omitted (no such concept in the data model). Two-way `open` lets
 * a trigger (e.g. the Focus FAB) show it; `created` fires with the new task so the host reloads.
 */
@Component({
  selector: 'app-task-create-drawer',
  imports: [FormsModule, TagChipsInputComponent, ProjectPickerComponent],
  templateUrl: './task-create-drawer.component.html',
  styleUrls: ['./task-create-drawer.component.css'],
  host: { '(document:keydown.escape)': 'onEscape()' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskCreateDrawerComponent {
  readonly open = model(false);
  readonly created = output<Task>();

  private readonly taskService = inject(TaskService);
  readonly saving = signal(false);

  readonly priorityOptions: { value: number; label: string; accent: string }[] = [
    { value: 1, label: 'Low', accent: 'low' },
    { value: 2, label: 'Normal', accent: 'normal' },
    { value: 4, label: 'High', accent: 'high' },
  ];

  draft: Draft = this.blank();

  constructor() {
    // Start each opening from a clean draft.
    effect(() => {
      if (this.open()) this.draft = this.blank();
    });
  }

  private blank(): Draft {
    return { title: '', priority: 2, description: '', for_today: false, tags: [] };
  }

  close(): void {
    this.open.set(false);
  }

  onEscape(): void {
    if (this.open()) this.close();
  }

  setPriority(value: number): void {
    this.draft.priority = value;
  }

  /** ISO/Date value → `yyyy-MM-ddThh:mm` for `<input type="datetime-local">`. */
  dateForInput(value?: string): string {
    if (!value) return '';
    const d = new Date(value);
    if (isNaN(d.getTime())) return '';
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  onDeadlineChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.draft.end_date = value ? new Date(value).toISOString() : undefined;
  }

  submit(): void {
    const title = this.draft.title.trim();
    if (!title || this.saving()) return;
    this.saving.set(true);

    const task: Task = {
      title,
      description: this.draft.description.trim() || undefined,
      estimated_time: this.draft.estimated_time,
      priority: this.draft.priority,
      for_today: this.draft.for_today,
      project: this.draft.project,
      tags: [],
      _tags: this.draft.tags,
    };
    // end_date is an ISO string; the model types it as Date, so assign through a cast (as task-detail does).
    if (this.draft.end_date) (task as unknown as Record<string, unknown>)['end_date'] = this.draft.end_date;

    this.taskService.addTask(task).subscribe({
      next: (created) => {
        this.saving.set(false);
        this.created.emit(created);
        this.open.set(false);
      },
      error: () => this.saving.set(false),
    });
  }
}
