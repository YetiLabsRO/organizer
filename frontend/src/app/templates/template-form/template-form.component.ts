import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { NgClass } from '@angular/common';
import { ReactiveFormsModule, UntypedFormBuilder, UntypedFormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TagInputModule } from 'ngx-chips';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { TaskTemplateService } from '../task-template.service';
import { Frequency, TaskTemplate, WEEKDAY_LABELS } from '../task-template';
import { ProjectService } from '../../projects/project.service';
import { Project } from '../../projects/project';
import { TagService } from '../../tags/tag.service';
import { Tag } from '../../tags/tag';

@Component({
  selector: 'app-template-form',
  imports: [ReactiveFormsModule, NgClass, TagInputModule, RouterLink],
  templateUrl: './template-form.component.html',
  styleUrls: ['./template-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TemplateFormComponent implements OnInit {
  private readonly formBuilder = inject(UntypedFormBuilder);
  private readonly templateService = inject(TaskTemplateService);
  private readonly projectService = inject(ProjectService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly tagService = inject(TagService);

  readonly weekdayLabels = WEEKDAY_LABELS;
  readonly priorities = [
    { value: 4, label: 'High' },
    { value: 2, label: 'Normal' },
    { value: 1, label: 'Low' },
  ];
  readonly months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  readonly template = signal<TaskTemplate | null>(null);
  readonly projects = signal<Project[]>([]);
  readonly showErrors = signal(false);
  readonly frequency = signal<Frequency>('monthly');
  readonly selectedWeekdays = signal<Set<number>>(new Set());

  templateForm = this.formBuilder.group({
    id: [null],
    title: ['', [Validators.required]],
    description: [''],
    priority: [2],
    estimated_time: [null],
    project: [null],
    frequency: ['monthly'],
    interval: [1, [Validators.required, Validators.min(1)]],
    day_of_month: [1],
    month_of_year: [1],
    lead_time_days: [0],
    skip_if_previous_open: [false],
    is_active: [true],
    start_on: [null],
    end_on: [null],
    _tags: [''],
  });

  ngOnInit(): void {
    this.projectService.getProjects().subscribe((projects) => this.projects.set(projects));

    this.templateForm.get('frequency')?.valueChanges.subscribe((value: Frequency) => this.frequency.set(value));

    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.templateService.getTemplate(id).subscribe((template) => {
        this.template.set(template);
        this.templateForm.patchValue(template);
        this.frequency.set(template.frequency);
        this.selectedWeekdays.set(new Set(template.weekdays ?? []));
      });
    }
  }

  toggleWeekday(value: number): void {
    const next = new Set(this.selectedWeekdays());
    if (next.has(value)) {
      next.delete(value);
    } else {
      next.add(value);
    }
    this.selectedWeekdays.set(next);
  }

  isWeekdaySelected(value: number): boolean {
    return this.selectedWeekdays().has(value);
  }

  searchTags(): (text: string) => Observable<Tag[]> {
    return (text: string) => this.tagService.searchTags(text);
  }

  private buildPayload(): TaskTemplate {
    const value = this.templateForm.value;
    const frequency: Frequency = value.frequency;
    const payload: TaskTemplate = {
      ...value,
      // Only send the recurrence fields relevant to the chosen frequency; null the rest so stale
      // values from switching frequency don't linger.
      weekdays: frequency === 'weekly' ? [...this.selectedWeekdays()].sort((a, b) => a - b) : null,
      day_of_month: frequency === 'monthly' || frequency === 'yearly' ? value.day_of_month : null,
      month_of_year: frequency === 'yearly' ? value.month_of_year : null,
      // Blank optional inputs come through as '' — normalise to null for the API.
      description: value.description || null,
      estimated_time: value.estimated_time || null,
      project: value.project || null,
      start_on: value.start_on || null,
      end_on: value.end_on || null,
    };
    return payload;
  }

  applyErrorsOnForm(form: UntypedFormGroup, errors: { error: any }): void {
    Object.keys(errors.error).forEach((field) => {
      form.get(field)?.setErrors({ serverError: errors.error[field] });
    });
    form.setErrors({ serverError: errors.error['non_field_errors'] });
  }

  onSubmit(): void {
    if (this.templateForm.invalid) {
      this.showErrors.set(true);
      return;
    }

    const payload = this.buildPayload();
    const save$ = payload.id
      ? this.templateService.updateTemplate(payload)
      : this.templateService.createTemplate(payload);

    save$
      .pipe(
        catchError((errors) => {
          this.applyErrorsOnForm(this.templateForm, errors);
          this.showErrors.set(true);
          return throwError(errors);
        }),
      )
      .subscribe({
        next: () => this.router.navigate(['templates']),
        error: () => this.showErrors.set(true),
      });
  }

  onDelete(): void {
    const id = this.templateForm.get('id')?.value;
    if (!id || !confirm('Delete this template?')) {
      return;
    }
    this.templateService.deleteTemplate(id).subscribe(() => this.router.navigate(['templates']));
  }
}
