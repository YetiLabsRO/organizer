import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TaskTemplateService } from '../task-template.service';
import { TaskTemplate } from '../task-template';
import { ReverseLuminanceColorPipe } from '../../reverse-luminance-color.pipe';

@Component({
  selector: 'app-template-list',
  imports: [RouterLink, ReverseLuminanceColorPipe],
  templateUrl: './template-list.component.html',
  styleUrls: ['./template-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TemplateListComponent implements OnInit {
  private readonly templateService = inject(TaskTemplateService);

  readonly templates = signal<TaskTemplate[] | null>(null);
  readonly busy = signal<number | null>(null);

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.templateService.getTemplates().subscribe((templates) => this.templates.set(templates));
  }

  runNow(template: TaskTemplate): void {
    if (template.id == null) {
      return;
    }
    this.busy.set(template.id);
    this.templateService.runTemplate(template.id).subscribe({
      next: () => {
        this.busy.set(null);
        this.reload();
      },
      error: () => this.busy.set(null),
    });
  }

  toggleActive(template: TaskTemplate): void {
    if (template.id == null) {
      return;
    }
    this.busy.set(template.id);
    this.templateService.updateTemplate({ ...template, is_active: !template.is_active }).subscribe({
      next: () => {
        this.busy.set(null);
        this.reload();
      },
      error: () => this.busy.set(null),
    });
  }

  remove(template: TaskTemplate): void {
    if (template.id == null || !confirm(`Delete template “${template.title}”?`)) {
      return;
    }
    this.templateService.deleteTemplate(template.id).subscribe(() => this.reload());
  }
}
