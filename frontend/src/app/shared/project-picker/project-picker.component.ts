import { ChangeDetectionStrategy, Component, ElementRef, effect, model, signal, viewChild } from '@angular/core';
import { Project } from '../../projects/project';
import { ProjectService } from '../../projects/project.service';
import { SuggestionListComponent, Suggestion } from '../autocomplete/suggestion-list.component';

/** Single-select project picker with type-to-filter autocomplete (mirrors quick-add's `@project`). */
@Component({
  selector: 'app-project-picker',
  imports: [SuggestionListComponent],
  templateUrl: './project-picker.component.html',
  styleUrls: ['./project-picker.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProjectPickerComponent {
  readonly projectId = model<number | undefined>(undefined);

  readonly text = signal('');
  readonly suggestions = signal<Suggestion[]>([]);
  readonly activeIndex = signal(0);
  readonly dropdownOpen = signal(false);

  private readonly projects = signal<Project[]>([]);
  private readonly inputRef = viewChild.required<ElementRef<HTMLInputElement>>('input');

  constructor(private projectService: ProjectService) {
    this.projectService.getProjectsCached().subscribe((projects) => this.projects.set(projects));
    // Keep the input reflecting the selected project, except while actively searching.
    effect(() => {
      const id = this.projectId();
      const project = id != null ? this.projects().find((p) => p.id === id) : undefined;
      if (!this.dropdownOpen()) {
        this.text.set(project ? project.title : '');
      }
    });
  }

  onInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.text.set(value);
    const q = value.replace(/^@/, '').toLowerCase();
    this.suggestions.set(
      this.projects()
        .filter((p) => p.title.toLowerCase().includes(q) || p.slug.toLowerCase().includes(q))
        .slice(0, 8)
        .map((p) => ({ id: p.id!, label: p.title, token: p.slug })),
    );
    this.activeIndex.set(0);
    this.dropdownOpen.set(true);
  }

  onKeydown(event: KeyboardEvent): void {
    if (!this.dropdownOpen()) return;
    const items = this.suggestions();
    if (event.key === 'ArrowDown' && items.length) {
      event.preventDefault();
      this.activeIndex.set((this.activeIndex() + 1) % items.length);
    } else if (event.key === 'ArrowUp' && items.length) {
      event.preventDefault();
      this.activeIndex.set((this.activeIndex() - 1 + items.length) % items.length);
    } else if ((event.key === 'Enter' || event.key === 'Tab') && items.length) {
      event.preventDefault();
      this.select(items[this.activeIndex()]);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      this.closeDropdown();
    }
  }

  select(suggestion: Suggestion): void {
    this.projectId.set(suggestion.id);
    this.closeDropdown();
  }

  clear(): void {
    this.projectId.set(undefined);
    this.text.set('');
  }

  onBlur(): void {
    this.closeDropdown();
  }

  private closeDropdown(): void {
    this.dropdownOpen.set(false);
    this.suggestions.set([]);
    this.activeIndex.set(0);
  }
}
