import { ChangeDetectionStrategy, Component, OnInit, signal } from '@angular/core';
import { DatePipe, NgClass } from '@angular/common';
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
  imports: [
    FormsModule, NgClass, DatePipe, RouterLink, MarkdownComponent, TagChipsInputComponent,
    ProjectPickerComponent,
  ],
  templateUrl: './task-detail.component.html',
  styleUrls: ['./task-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskDetailComponent implements OnInit {
  readonly task = signal<Task | undefined>(undefined);
  readonly saving = signal(false);
  readonly previewOnly = signal(false);

  /** New-comment draft + in-flight flag for the comments section. */
  readonly newComment = signal('');
  readonly addingComment = signal(false);

  /** Priority as a segmented control: traffic-light accents + a magnitude bar count. */
  readonly priorityOptions: { value: number; label: string; bars: number; accent: 'low' | 'normal' | 'high' }[] = [
    { value: 1, label: 'Low', bars: 1, accent: 'low' },
    { value: 2, label: 'Normal', bars: 2, accent: 'normal' },
    { value: 4, label: 'High', bars: 3, accent: 'high' },
  ];

  /** Status DAG — the happy path (Idea → In progress → Done) and the states that branch off it. */
  readonly flowMain = [
    { value: 'idea', label: 'Idea', icon: 'lightbulb', accent: 'idea' },
    { value: 'inprogress', label: 'In progress', icon: 'arrow-repeat', accent: 'progress' },
  ];
  readonly flowBranch = [
    { value: 'blocked', label: 'Blocked', icon: 'slash-circle', accent: 'blocked' },
    { value: 'givenup', label: 'Given up', icon: 'flag', accent: 'givenup' },
  ];

  /** One-shot flag that fires the completion burst only on a user toggle (not on load). */
  readonly celebrate = signal(false);

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
    if (task.completed) this.celebrate.set(true);
    this.task.set({ ...task });
    this.save();
  }

  /** Set the task's status from a DAG node (persisted on Save, like the other form fields). */
  setStatus(value: string): void {
    const task = this.task();
    if (!task) return;
    this.task.set({ ...task, status: value });
  }

  /** Set the task's priority from the segmented control. */
  setPriority(value: number): void {
    const task = this.task();
    if (!task) return;
    this.task.set({ ...task, priority: value });
  }

  /** Segment index (0–2) driving the sliding thumb; defaults to Normal's slot. */
  priorityIndex(priority?: number): number {
    const i = this.priorityOptions.findIndex((p) => p.value === priority);
    return i < 0 ? 1 : i;
  }

  /** Traffic-light accent name for the current priority (low/normal/high). */
  priorityAccent(priority?: number): string {
    return this.priorityOptions.find((p) => p.value === priority)?.accent ?? 'normal';
  }

  addComment(): void {
    const task = this.task();
    const text = this.newComment().trim();
    if (!task?.id || !text || this.addingComment()) return;
    this.addingComment.set(true);
    this.taskService.addComment(task.id, text).subscribe({
      next: (comment) => {
        // The list is server-ordered oldest→newest; append so the newest shows at the bottom.
        task.comments = [...(task.comments ?? []), comment];
        this.task.set({ ...task });
        this.newComment.set('');
        this.addingComment.set(false);
      },
      error: () => this.addingComment.set(false),
    });
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
