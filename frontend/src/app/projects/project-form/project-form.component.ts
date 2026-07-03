import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { NgClass } from '@angular/common';
import { ReactiveFormsModule, UntypedFormBuilder, UntypedFormGroup, Validators } from '@angular/forms';
import { NgbModule, NgbDate } from '@ng-bootstrap/ng-bootstrap';
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
          //  complains about otherwise (.tags, in this case)
          this.projectForm.patchValue(project);

          const azi = new Date();
          this.projectForm.get('start_date')?.setValue({ 'year': azi.getFullYear(), 'month': azi.getMonth(), 'day': azi.getDay() });
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

  onSubmit(): void {
    if (this.projectForm.invalid) {
      this.showErrors.set(true);
      return;
    }

    this.projectService
      .createProject(<Project>this.projectForm.value)
      .pipe(catchError(errors => {
        this.applyErrorsOnForm(this.projectForm, errors);
        this.showErrors.set(true);
        return throwError(errors);
      }))
      .subscribe({
        next: newProject => {
          this.project.set(newProject);
          this.showErrors.set(false);
          this.router.navigate(['projects', newProject.id]);
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
