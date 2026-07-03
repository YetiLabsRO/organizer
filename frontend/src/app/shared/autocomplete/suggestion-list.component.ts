import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

export interface Suggestion {
  id: number;
  label: string;
  /** Canonical token text inserted on select (e.g. the slug), if different from `label`. */
  token?: string;
  /** Background colour for tag suggestions (hex). */
  color?: string;
  /** Contrasting text colour computed for `color`. */
  textColor?: string;
  /** Secondary text (e.g. tag usage count). */
  hint?: string;
}

/**
 * Presentational dropdown of autocomplete suggestions. The consumer positions it
 * (absolutely) under its input and owns the active-index/keyboard state.
 */
@Component({
  selector: 'app-suggestion-list',
  template: `
    <ul class="suggestion-list list-group shadow-sm">
      @for (item of items(); track item.id; let i = $index) {
        <li
          class="suggestion-item list-group-item list-group-item-action d-flex align-items-center gap-2"
          [class.active]="i === activeIndex()"
          (mousedown)="$event.preventDefault(); pick.emit(item)"
          (mouseenter)="activeChange.emit(i)"
        >
          @if (item.color) {
            <span class="badge rounded-pill" [style.background-color]="item.color" [style.color]="item.textColor">
              {{ item.label }}
            </span>
          } @else {
            <span class="flex-grow-1 text-truncate">{{ item.label }}</span>
          }
          @if (item.hint) {
            <small class="text-muted ms-auto">{{ item.hint }}</small>
          }
        </li>
      } @empty {
        <li class="list-group-item text-muted small">No matches</li>
      }
    </ul>
  `,
  styleUrls: ['./suggestion-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SuggestionListComponent {
  readonly items = input<Suggestion[]>([]);
  readonly activeIndex = input(0);
  readonly pick = output<Suggestion>();
  readonly activeChange = output<number>();
}
