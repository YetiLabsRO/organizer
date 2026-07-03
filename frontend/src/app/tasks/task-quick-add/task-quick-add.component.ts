import { ChangeDetectionStrategy, Component, ElementRef, signal, output, viewChild } from '@angular/core';
import { forkJoin, of, Subject } from 'rxjs';
import { debounceTime, switchMap } from 'rxjs/operators';
import { TagService } from '../../tags/tag.service';
import { ProjectService } from '../../projects/project.service';
import { Project } from '../../projects/project';
import { Tag } from '../../tags/tag';
import { SuggestionListComponent, Suggestion } from '../../shared/autocomplete/suggestion-list.component';
import { tagTextColor } from '../../shared/tag-color.util';

export interface NewTaskRequest {
  title: string;
  tags: Tag[];
  project?: number;
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
  private readonly query$ = new Subject<{ trigger: Trigger; query: string }>();

  constructor(private tagService: TagService, private projectService: ProjectService) {
    this.projectService.getProjectsCached().subscribe((projects) => (this.projects = projects));

    this.query$
      .pipe(
        debounceTime(150),
        switchMap(({ trigger, query }) =>
          trigger === '#'
            ? this.tagService.searchTags(query)
            : of(this.filterProjects(query)),
        ),
      )
      .subscribe((results) => {
        const suggestions = this.trigger === '#'
          ? (results as Tag[]).map((t) => this.tagSuggestion(t))
          : (results as Project[]).map((p) => this.projectSuggestion(p));
        this.suggestions.set(suggestions);
        this.activeIndex.set(0);
      });
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
      this.query$.next({ trigger: token.trigger, query: token.query });
    } else {
      this.closeDropdown();
    }
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

    const tagSlugs = [...raw.matchAll(/(?:^|\s)#([\w-]+)/g)].map((m) => m[1]);
    const projectSlug = raw.match(/(?:^|\s)@([\w-]+)/)?.[1];
    const title = raw.replace(/(?:^|\s)[#@][\w-]+/g, ' ').replace(/\s+/g, ' ').trim();
    if (!title) return;

    const project = projectSlug ? this.projects.find((p) => p.slug === projectSlug)?.id : undefined;

    if (tagSlugs.length === 0) {
      this.emit(title, [], project);
      return;
    }
    forkJoin(tagSlugs.map((slug) => this.tagService.getTagBySlug(slug))).subscribe((groups) => {
      const tags = groups.flatMap((found) => (found.length ? [found[0]] : []));
      this.emit(title, tags, project);
    });
  }

  closeDropdown(): void {
    this.dropdownOpen.set(false);
    this.suggestions.set([]);
    this.activeIndex.set(0);
    this.trigger = null;
  }

  private emit(title: string, tags: Tag[], project?: number): void {
    this.create.emit({ title, tags, project });
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
