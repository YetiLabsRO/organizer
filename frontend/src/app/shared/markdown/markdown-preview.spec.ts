import { marked } from 'marked';

import { toPreviewHtml } from './markdown-preview';

/** Parse Markdown the way MarkdownComponent does, then cut it to `limit` visible characters. */
function preview(markdown: string, limit: number): string {
  return toPreviewHtml(marked.parse(markdown, { async: false, gfm: true, breaks: true }) as string, limit);
}

/** The text a reader actually sees, with the markup stripped back off. */
function text(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  return doc.body.textContent ?? '';
}

describe('toPreviewHtml', () => {
  it('leaves a description that fits alone', () => {
    expect(preview('Short and sweet.', 160)).toContain('Short and sweet.');
    expect(preview('Short and sweet.', 160)).not.toContain('…');
  });

  it('cuts an overlong description to the budget and marks it with an ellipsis', () => {
    const out = preview('word '.repeat(100), 40);
    expect(out).toContain('…');
    expect(text(out).length).toBeLessThanOrEqual(41); // 40 visible characters + the ellipsis
  });

  it('cuts on a word boundary rather than mid-word', () => {
    expect(text(preview('alpha bravo charlie delta', 16))).toBe('alpha bravo…');
  });

  it('cuts mid-word rather than collapsing the preview when one word eats the budget', () => {
    expect(text(preview('a supercalifragilisticexpialidocious', 12))).toBe('a supercalif…');
  });

  it('renders the emphasis that straddles the cut instead of stranding its markers', () => {
    const out = preview('Plain **bold text that runs on and on**', 14);
    expect(out).toContain('<strong>');
    expect(text(out)).not.toContain('*');
  });

  it('keeps a link that only partly fits as a working link', () => {
    const out = preview('See [the full documentation page](https://example.com/docs) now', 12);
    expect(out).toContain('href="https://example.com/docs"');
    expect(text(out)).not.toContain('](');
  });

  it('drops whatever follows the cut', () => {
    const out = preview('First paragraph.\n\nSecond paragraph.', 6);
    expect(text(out)).not.toContain('Second');
  });

  it('keeps the word break a <br> stood for', () => {
    expect(text(preview('alpha\nbravo', 160)).replace(/\s+/g, ' ').trim()).toBe('alpha bravo');
  });

  it('substitutes alt text for an image, which cannot render on one line', () => {
    const out = preview('![a diagram](https://example.com/x.png) follows', 160);
    expect(out).not.toContain('<img');
    expect(text(out)).toContain('a diagram');
  });

  it('drops an image that has no alt text', () => {
    expect(text(preview('![](https://example.com/x.png) tail', 160)).trim()).toBe('tail');
  });

  it('flattens a code block onto one line', () => {
    const out = preview('```\nconst a = 1;\nconst b = 2;\n```', 160);
    expect(text(out)).not.toContain('\n');
  });

  it('does not spend the budget on whitespace the browser collapses anyway', () => {
    expect(text(preview('alpha\n\nbravo\n\ncharlie', 20))).not.toContain('…');
  });
});
