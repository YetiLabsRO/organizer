import { ChangeDetectionStrategy, Component, ElementRef, computed, model, signal, viewChild } from '@angular/core';
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
  /** Guarded view of the model: `[(tags)]` may be bound to an undefined `_tags`. */
  readonly currentTags = computed(() => this.tags() ?? []);

  readonly text = signal('');
  readonly suggestions = signal<Suggestion[]>([]);
  readonly activeIndex = signal(0);
  readonly dropdownOpen = signal(false);

  readonly textColor = tagTextColor;

  private readonly inputRef = viewChild.required<ElementRef<HTMLInputElement>>('input');
  private readonly tagsById = new Map<number, Tag>();
  /** Full tag list, loaded once; filtered client-side (the API doesn't filter tags by name). */
  private allTags: Tag[] = [];

  constructor(private tagService: TagService) {
    this.tagService.getTagsCached().subscribe((tags) => {
      this.allTags = tags;
      tags.forEach((t) => this.tagsById.set(t.id, t));
    });
  }

  private refreshSuggestions(query: string): void {
    const q = query.toLowerCase();
    const selected = new Set(this.currentTags().map((t) => t.id));
    this.suggestions.set(
      this.allTags
        .filter((t) => !selected.has(t.id))
        .filter((t) => t.name.toLowerCase().includes(q) || t.slug.toLowerCase().includes(q))
        .slice(0, 10)
        .map((t) => this.toSuggestion(t)),
    );
    this.activeIndex.set(0);
  }

  onInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.text.set(value);
    this.dropdownOpen.set(true);
    this.refreshSuggestions(value.replace(/^#/, '').trim());
  }

  onFocus(): void {
    this.dropdownOpen.set(true);
    this.refreshSuggestions(this.text().replace(/^#/, '').trim());
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
    if (event.key === 'Backspace' && this.text() === '' && this.currentTags().length) {
      event.preventDefault();
      this.remove(this.currentTags()[this.currentTags().length - 1]);
    }
  }

  selectSuggestion(suggestion: Suggestion): void {
    const tag = this.tagsById.get(suggestion.id);
    if (tag && !this.currentTags().some((t) => t.id === tag.id)) {
      this.tags.set([...this.currentTags(), tag]);
    }
    this.text.set('');
    this.closeDropdown();
    queueMicrotask(() => this.inputRef().nativeElement.focus());
  }

  remove(tag: Tag): void {
    this.tags.set(this.currentTags().filter((t) => t.id !== tag.id));
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
