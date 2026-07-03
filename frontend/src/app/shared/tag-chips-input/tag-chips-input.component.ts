import { ChangeDetectionStrategy, Component, ElementRef, model, signal, viewChild } from '@angular/core';
import { Subject } from 'rxjs';
import { debounceTime, switchMap } from 'rxjs/operators';
import { Tag } from '../../tags/tag';
import { TagService } from '../../tags/tag.service';
import { SuggestionListComponent, Suggestion } from '../autocomplete/suggestion-list.component';
import { tagTextColor } from '../tag-color.util';

/**
 * Seamless tag editor: colored, removable chips plus a single input with `#`
 * autocomplete (existing tags only). One control — no duplicated tag display.
 */
@Component({
  selector: 'app-tag-chips-input',
  imports: [SuggestionListComponent],
  templateUrl: './tag-chips-input.component.html',
  styleUrls: ['./tag-chips-input.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TagChipsInputComponent {
  readonly tags = model<Tag[]>([]);

  readonly text = signal('');
  readonly suggestions = signal<Suggestion[]>([]);
  readonly activeIndex = signal(0);
  readonly dropdownOpen = signal(false);

  readonly textColor = tagTextColor;

  private readonly inputRef = viewChild.required<ElementRef<HTMLInputElement>>('input');
  private readonly tagsById = new Map<number, Tag>();
  private readonly query$ = new Subject<string>();

  constructor(private tagService: TagService) {
    this.query$
      .pipe(
        debounceTime(150),
        switchMap((q) => this.tagService.searchTags(q)),
      )
      .subscribe((tags) => {
        const selected = new Set(this.tags().map((t) => t.id));
        const available = tags.filter((t) => !selected.has(t.id));
        available.forEach((t) => this.tagsById.set(t.id, t));
        this.suggestions.set(available.map((t) => this.toSuggestion(t)));
        this.activeIndex.set(0);
      });
  }

  onInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.text.set(value);
    const query = value.replace(/^#/, '').trim();
    if (query.length === 0 && value !== '#') {
      this.closeDropdown();
      return;
    }
    this.dropdownOpen.set(true);
    this.query$.next(query);
  }

  onKeydown(event: KeyboardEvent): void {
    const items = this.suggestions();
    if (this.dropdownOpen()) {
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
        this.selectSuggestion(items[this.activeIndex()]);
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        this.closeDropdown();
        return;
      }
    }
    if (event.key === 'Backspace' && this.text() === '' && this.tags().length) {
      event.preventDefault();
      this.remove(this.tags()[this.tags().length - 1]);
    }
  }

  selectSuggestion(suggestion: Suggestion): void {
    const tag = this.tagsById.get(suggestion.id);
    if (tag && !this.tags().some((t) => t.id === tag.id)) {
      this.tags.set([...this.tags(), tag]);
    }
    this.text.set('');
    this.closeDropdown();
    queueMicrotask(() => this.inputRef().nativeElement.focus());
  }

  remove(tag: Tag): void {
    this.tags.set(this.tags().filter((t) => t.id !== tag.id));
  }

  closeDropdown(): void {
    this.dropdownOpen.set(false);
    this.suggestions.set([]);
    this.activeIndex.set(0);
  }

  private toSuggestion(tag: Tag): Suggestion {
    return {
      id: tag.id,
      label: tag.name,
      color: tag.color,
      textColor: tagTextColor(tag.color),
      hint: tag.count ? `${tag.count}` : undefined,
    };
  }
}
