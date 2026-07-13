import { ChangeDetectionStrategy, Component, ElementRef, signal, output, viewChild } from '@angular/core';
import { forkJoin } from 'rxjs';
import { TagService } from '../../tags/tag.service';
import { ProjectService } from '../../projects/project.service';
import { Project } from '../../projects/project';
import { Tag } from '../../tags/tag';
import { SuggestionListComponent, Suggestion } from '../../shared/autocomplete/suggestion-list.component';
import { tagTextColor } from '../../shared/tag-color.util';
import { QuickAddParse, parseQuickAdd, stripTokens } from '../quick-add-parse';

export interface NewTaskRequest {
  title: string;
  tags: Tag[];
  project?: number;
  priority?: number;
  endDate?: Date;
}

type Trigger = '#' | '@';

/**
 * Quick-add field with inline `#tag` / `@project` autocomplete.
 *
 * Typing `#` or `@` (at the start or after whitespace) opens a dropdown of matching
 * tags (in their colours) or projects; selecting inserts the canonical `#slug`/`@slug`.
 * On submit the tokens are resolved to ids and stripped from the title.
 */
@Component({
  selector: 'app-task-quick-add',
  imports: [SuggestionListComponent],
  templateUrl: './task-quick-add.component.html',
  styleUrls: ['./task-quick-add.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskQuickAddComponent {
  readonly create = output<NewTaskRequest>();

  readonly text = signal('');
  readonly suggestions = signal<Suggestion[]>([]);
  readonly activeIndex = signal(0);
  readonly dropdownOpen = signal(false);

  private readonly inputRef = viewChild.required<ElementRef<HTMLInputElement>>('input');

  private trigger: Trigger | null = null;
  private tokenStart = -1;
  private tokenEnd = -1;
  private projects: Project[] = [];
  private tags: Tag[] = [];

  constructor(private tagService: TagService, private projectService: ProjectService) {
    this.projectService.getProjectsCached().subscribe((projects) => (this.projects = projects));
    this.tagService.getTagsCached().subscribe((tags) => (this.tags = tags));
  }

  /** Put the caret in the field (used by the list's `c` shortcut). */
  focus(): void {
    this.inputRef().nativeElement.focus();
  }

  onInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.text.set(input.value);
    const caret = input.selectionStart ?? input.value.length;
    const token = this.detectToken(input.value, caret);
    if (token) {
      this.trigger = token.trigger;
      this.tokenStart = token.start;
      this.tokenEnd = caret;
      this.dropdownOpen.set(true);
      this.refreshSuggestions(token.trigger, token.query);
    } else {
      this.closeDropdown();
    }
  }

  private refreshSuggestions(trigger: Trigger, query: string): void {
    const suggestions: Suggestion[] = trigger === '#'
      ? this.filterTags(query).map((t) => this.tagSuggestion(t))
      : this.filterProjects(query).map((p) => this.projectSuggestion(p));
    this.suggestions.set(suggestions);
    this.activeIndex.set(0);
  }

  private filterTags(query: string): Tag[] {
    const q = query.toLowerCase();
    return this.tags
      .filter((t) => t.name.toLowerCase().includes(q) || t.slug.toLowerCase().includes(q))
      .slice(0, 8);
  }

  onKeydown(event: KeyboardEvent): void {
    if (this.dropdownOpen()) {
      const items = this.suggestions();
      if (event.key === 'ArrowDown' && items.length) {
        event.preventDefault();
        this.activeIndex.set((this.activeIndex() + 1) % items.length);
        return;
      }
      if (event.key === 'ArrowUp' && items.length) {
        event.preventDefault();
        this.activeIndex.set((this.activeIndex() - 1 + items.length) % items.length);
        return;
      }
      if ((event.key === 'Enter' || event.key === 'Tab') && items.length) {
        event.preventDefault();
        this.select(items[this.activeIndex()]);
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        this.closeDropdown();
        return;
      }
    }
    if (event.key === 'Enter') {
      this.submit();
    }
  }

  select(item: Suggestion): void {
    const canonical = `${this.trigger}${item.token ?? item.label}`;
    const value = this.text();
    const before = value.slice(0, this.tokenStart);
    const after = value.slice(this.tokenEnd);
    const spacer = after.startsWith(' ') ? '' : ' ';
    const next = `${before}${canonical}${spacer}${after}`;
    this.text.set(next);
    this.closeDropdown();

    const caret = (before + canonical + spacer).length;
    queueMicrotask(() => {
      const el = this.inputRef().nativeElement;
      el.focus();
      el.setSelectionRange(caret, caret);
    });
  }

  submit(): void {
    const raw = this.text().trim();
    if (!raw) return;

    const parsed = parseQuickAdd(raw);

    // A project token only counts if it names a real project; otherwise it stays as text.
    const project = parsed.projectSlug
      ? this.projects.find((p) => p.slug.toLowerCase() === parsed.projectSlug!.toLowerCase())
      : undefined;

    if (parsed.tagSlugs.length === 0) {
      this.emit(parsed, [], [], project?.id, project?.slug);
      return;
    }

    // Resolve every #tag before building the title: only the ones that exist get stripped,
    // so an unknown #tag survives as literal text instead of vanishing from the task.
    forkJoin(parsed.tagSlugs.map((slug) => this.tagService.getTagBySlug(slug))).subscribe((groups) => {
      const tags = groups.flatMap((found) => (found.length ? [found[0]] : []));
      const resolvedSlugs = parsed.tagSlugs.filter((_, i) => groups[i].length > 0);
      this.emit(parsed, tags, resolvedSlugs, project?.id, project?.slug);
    });
  }

  closeDropdown(): void {
    this.dropdownOpen.set(false);
    this.suggestions.set([]);
    this.activeIndex.set(0);
    this.trigger = null;
  }

  /** Build the final title from the tokens that actually resolved, then emit. */
  private emit(
    parsed: QuickAddParse,
    tags: Tag[],
    resolvedTagSlugs: string[],
    projectId?: number,
    projectSlug?: string,
  ): void {
    const title = stripTokens(parsed.text, resolvedTagSlugs, projectSlug);
    if (!title) return;

    this.create.emit({
      title,
      tags,
      project: projectId,
      priority: parsed.priority,
      endDate: parsed.endDate,
    });
    this.text.set('');
    this.closeDropdown();
  }

  private detectToken(value: string, caret: number): { trigger: Trigger; query: string; start: number } | null {
    const upto = value.slice(0, caret);
    const match = upto.match(/(?:^|\s)([#@])([\w-]*)$/);
    if (!match) return null;
    const trigger = match[1] as Trigger;
    const query = match[2];
    return { trigger, query, start: caret - query.length - 1 };
  }

  private filterProjects(query: string): Project[] {
    const q = query.toLowerCase();
    return this.projects
      .filter((p) => p.title.toLowerCase().includes(q) || p.slug.toLowerCase().includes(q))
      .slice(0, 8);
  }

  private tagSuggestion(tag: Tag): Suggestion {
    return {
      id: tag.id,
      label: tag.name,
      token: tag.slug,
      color: tag.color,
      textColor: tagTextColor(tag.color),
      hint: tag.count ? `${tag.count}` : undefined,
    };
  }

  private projectSuggestion(project: Project): Suggestion {
    return { id: project.id!, label: project.title, token: project.slug };
  }
}
