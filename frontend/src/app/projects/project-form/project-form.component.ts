import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { NgClass } from '@angular/common';
import { ReactiveFormsModule, UntypedFormBuilder, UntypedFormGroup, Validators } from '@angular/forms';
import { NgbModule, NgbDate, NgbDateStruct } from '@ng-bootstrap/ng-bootstrap';
import { TagInputModule } from 'ngx-chips';
import { ProjectService } from '../project.service';
import { Project } from '../project';
import { TagService } from '../../tags/tag.service';
import { Observable, throwError } from 'rxjs';
import { Tag } from '../../tags/tag';
import { ActivatedRoute, Router } from '@angular/router';
import { catchError } from 'rxjs/operators';
import { ReverseLuminanceColorPipe } from '../../reverse-luminance-color.pipe';

@Component({
  selector: 'app-project-form',
  imports: [ReactiveFormsModule, NgClass, NgbModule, TagInputModule, ReverseLuminanceColorPipe],
  templateUrl: './project-form.component.html',
  styleUrls: ['./project-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProjectFormComponent implements OnInit {
  private formBuilder = inject(UntypedFormBuilder);

  projectForm = this.formBuilder.group({
      id: [null],
      slug: [null],
      title: ['', [Validators.required]],
      description: [''],
      start_date: [null],
      end_date: [null],
      _tags: ['']
    }
  );

  readonly project = signal<Project | null>(null);
  readonly showErrors = signal(false);

  constructor(
    private projectService: ProjectService,
    public tagService: TagService,
    private route: ActivatedRoute,
    private router: Router,
  ) {
  }

  ngOnInit(): void {
    const projectId = this.route.snapshot.paramMap.get('id');
    if (projectId) {
      this.projectService.getProject(projectId).subscribe(project => {
        this.project.set(project);
        if (project) {
          //  using patch value here because Project has additional fields that the form
          //  complains about otherwise (.tags, in this case). The dates arrive as `DD/MM/YYYY`
          //  strings and have to become datepicker structs, or the picker shows nothing and the
          //  API rejects what gets sent back.
          this.projectForm.patchValue({
            ...project,
            start_date: this.toDateStruct(project.start_date),
            end_date: this.toDateStruct(project.end_date),
          });
        }
      });
    } else {
      this.projectService.clearProject();
    }
  }

  updateSlug(): void {
    let value = this.projectForm.get('title')?.value;
    if (value) {
      this.projectForm.get('slug')?.setValue(value.toString().toLowerCase()
        .replace(/\s+/g, '-')           // Replace spaces with -
        .replace(/[^\w\-]+/g, '')       // Remove all non-word chars
        .replace(/\-\-+/g, '-')         // Replace multiple - with single -
        .replace(/^-+/, '')             // Trim - from start of text
        .replace(/-+$/, '')
      );
    } else {
      this.projectForm.get('slug')?.setValue('');
    }
  }

  applyErrorsOnForm(form: UntypedFormGroup, errors: { error: any }): void {
    Object.keys(errors.error).forEach(field => {
      const formControl = form.get(field);
      if (formControl) {
        formControl.setErrors({ serverError: errors.error[field] });
      }
    });

    form.setErrors({ serverError: errors.error['non_field_errors'] });
  }

  /** API date (`DD/MM/YYYY`) → the datepicker's `{year, month, day}`. */
  private toDateStruct(value: unknown): NgbDateStruct | null {
    if (typeof value !== 'string') {
      return null;
    }
    const parts = value.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    return parts ? { day: +parts[1], month: +parts[2], year: +parts[3] } : null;
  }

  /** The datepicker's `{year, month, day}` → an ISO date, the only format the API parses. */
  private fromDateStruct(value: any): string | null {
    if (!value) {
      return null;
    }
    if (typeof value === 'string') {
      return value;
    }
    const { year, month, day } = value as NgbDateStruct;
    if (!year || !month || !day) {
      return null;
    }
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${year}-${pad(month)}-${pad(day)}`;
  }

  onSubmit(): void {
    if (this.projectForm.invalid) {
      this.showErrors.set(true);
      return;
    }

    const value = this.projectForm.value;
    const project = <Project>{
      ...value,
      start_date: this.fromDateStruct(value.start_date),
      end_date: this.fromDateStruct(value.end_date),
    };

    // Editing an existing project updates it; only a form without an id creates one.
    const save = project.id
      ? this.projectService.updateProject(project)
      : this.projectService.createProject(project);

    save
      .pipe(catchError(errors => {
        this.applyErrorsOnForm(this.projectForm, errors);
        this.showErrors.set(true);
        return throwError(errors);
      }))
      .subscribe({
        next: savedProject => {
          this.project.set(savedProject);
          this.showErrors.set(false);
          this.router.navigate(['projects', savedProject.id]);
        },
        error: () => this.showErrors.set(true),
      });
  }

  public searchTags(): (text: string) => Observable<Tag[]> {
    return (text: string) => this.tagService.searchTags(text);
  }

  public onDateSelect(date: NgbDate): void {
  }
}
