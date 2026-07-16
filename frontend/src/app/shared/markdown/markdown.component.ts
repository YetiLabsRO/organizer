import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { marked } from 'marked';

import { toPreviewHtml } from './markdown-preview';

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
  /**
   * Cap the render at this many visible characters, cut on a word boundary and closed with an
   * ellipsis. 0 renders the whole description.
   */
  readonly limit = input(0);

  readonly html = computed<string>(() => {
    const text = this.value();
    if (!text) {
      return '';
    }
    const html = marked.parse(text, { async: false, gfm: true, breaks: true }) as string;
    const limit = this.limit();
    return limit > 0 ? toPreviewHtml(html, limit) : html;
  });
}
