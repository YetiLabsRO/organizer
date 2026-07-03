import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { marked } from 'marked';

/**
 * Renders a Markdown string to HTML.
 *
 * The parsed HTML is bound via `[innerHTML]`, which Angular's DomSanitizer scrubs
 * (scripts and event handlers are stripped) — so no `bypassSecurityTrust*` and no
 * extra sanitiser dependency is needed.
 */
@Component({
  selector: 'app-markdown',
  template: `<div class="markdown-body" [class.markdown-inline]="inline()" [innerHTML]="html()"></div>`,
  styleUrls: ['./markdown.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MarkdownComponent {
  readonly value = input<string | null | undefined>('');
  /** Inline mode: collapse block spacing so the render fits a single clamped row. */
  readonly inline = input(false);

  readonly html = computed<string>(() => {
    const text = this.value();
    if (!text) {
      return '';
    }
    return marked.parse(text, { async: false, gfm: true, breaks: true }) as string;
  });
}
