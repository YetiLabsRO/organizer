import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { TaskTemplateService } from '../task-template.service';
import { Frequency, TaskTemplate, WEEKDAY_LABELS } from '../task-template';
import { TagChipsInputComponent } from '../../shared/tag-chips-input/tag-chips-input.component';
import { ProjectPickerComponent } from '../../shared/project-picker/project-picker.component';

@Component({
  selector: 'app-template-form',
  imports: [FormsModule, RouterLink, TagChipsInputComponent, ProjectPickerComponent],
  templateUrl: './template-form.component.html',
  styleUrls: ['./template-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TemplateFormComponent implements OnInit {
  private readonly templateService = inject(TaskTemplateService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly template = signal<TaskTemplate | null>(null);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  readonly weekdayLabels = WEEKDAY_LABELS;

  /** Priority as a segmented control — same traffic-light accents as the task form. */
  readonly priorityOptions: { value: number; label: string; accent: 'low' | 'normal' | 'high' }[] = [
    { value: 1, label: 'Low', accent: 'low' },
    { value: 2, label: 'Normal', accent: 'normal' },
    { value: 4, label: 'High', accent: 'high' },
  ];
  readonly months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.templateService.getTemplate(id).subscribe((t) => {
        t._tags = t._tags ?? [];
        t.weekdays = t.weekdays ?? [];
        this.template.set(t);
      });
    } else {
      this.template.set(this.blank());
    }
  }

  private blank(): TaskTemplate {
    return {
      title: '',
      description: '',
      priority: 2,
      estimated_time: null,
      project: undefined,
      _tags: [],
      tags: [],
      frequency: 'monthly',
      interval: 1,
      day_of_month: 1,
      weekdays: [],
      month_of_year: 1,
      start_on: null,
      end_on: null,
      lead_time_days: 0,
      skip_if_previous_open: false,
      is_active: true,
    };
  }

  // --- priority segmented control ---
  setPriority(value: number): void {
    const t = this.template();
    if (t) this.template.set({ ...t, priority: value });
  }

  priorityIndex(priority?: number): number {
    const i = this.priorityOptions.findIndex((p) => p.value === priority);
    return i < 0 ? 1 : i;
  }

  priorityAccent(priority?: number): string {
    return this.priorityOptions.find((p) => p.value === priority)?.accent ?? 'normal';
  }

  // --- recurrence controls ---
  setFrequency(value: Frequency): void {
    const t = this.template();
    if (t) this.template.set({ ...t, frequency: value });
  }

  toggleWeekday(value: number): void {
    const t = this.template();
    if (!t) return;
    const set = new Set(t.weekdays ?? []);
    set.has(value) ? set.delete(value) : set.add(value);
    this.template.set({ ...t, weekdays: [...set].sort((a, b) => a - b) });
  }

  isWeekdaySelected(value: number): boolean {
    return (this.template()?.weekdays ?? []).includes(value);
  }

  // --- save / delete ---
  save(): void {
    const current = this.template();
    if (!current || !current.title?.trim() || this.saving()) return;

    // Only send the recurrence fields relevant to the chosen frequency; null the rest so stale
    // values from switching frequency don't linger. Blank optional inputs → null for the API.
    const payload: TaskTemplate = {
      ...current,
      weekdays: current.frequency === 'weekly' ? (current.weekdays ?? []) : null,
      day_of_month:
        current.frequency === 'monthly' || current.frequency === 'yearly' ? current.day_of_month : null,
      month_of_year: current.frequency === 'yearly' ? current.month_of_year : null,
      description: current.description || null,
      estimated_time: current.estimated_time || null,
      start_on: current.start_on || null,
      end_on: current.end_on || null,
    };

    this.saving.set(true);
    this.error.set(null);
    const save$ = payload.id
      ? this.templateService.updateTemplate(payload)
      : this.templateService.createTemplate(payload);

    save$.subscribe({
      next: () => this.router.navigate(['templates']),
      error: (err) => {
        this.saving.set(false);
        this.error.set(this.readError(err));
      },
    });
  }

  onDelete(): void {
    const t = this.template();
    if (t?.id == null || !confirm('Delete this template?')) return;
    this.templateService.deleteTemplate(t.id).subscribe(() => this.router.navigate(['templates']));
  }

  /** Flatten a DRF error body ({field: [msgs]} / {non_field_errors: […]}) into one line. */
  private readError(err: unknown): string {
    const body = (err as { error?: unknown })?.error;
    if (body && typeof body === 'object') {
      const parts = Object.entries(body as Record<string, unknown>).map(([field, msgs]) => {
        const text = Array.isArray(msgs) ? msgs.join(' ') : String(msgs);
        return field === 'non_field_errors' ? text : `${field}: ${text}`;
      });
      if (parts.length) return parts.join(' · ');
    }
    return 'Could not save the template. Please check the fields and try again.';
  }
}
