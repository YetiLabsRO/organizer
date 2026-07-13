import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

/** One shortcut: the keys that trigger it and what it does. */
export interface ShortcutHint {
  /** Key chips, rendered in order and joined with `+` (e.g. `['Ctrl', '1']`). */
  keys: string[];
  label: string;
}

export interface ShortcutGroup {
  title: string;
  items: ShortcutHint[];
}

/**
 * Modal panel listing the keyboard shortcuts a screen offers, opened with `?`.
 *
 * Content-agnostic: the host passes the `groups` it supports. Two-way `open` lets the host drive it
 * from a key handler; the panel closes itself on Escape, on the close button, and on a backdrop click.
 */
@Component({
  selector: 'app-keyboard-shortcuts',
  templateUrl: './keyboard-shortcuts.component.html',
  styleUrls: ['./keyboard-shortcuts.component.css'],
  host: { '(document:keydown.escape)': 'onEscape()' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KeyboardShortcutsComponent {
  readonly open = model(false);
  readonly groups = input.required<ShortcutGroup[]>();
  readonly title = input('Keyboard shortcuts');

  close(): void {
    this.open.set(false);
  }

  onEscape(): void {
    if (this.open()) this.close();
  }
}
