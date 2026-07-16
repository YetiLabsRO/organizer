const ELLIPSIS = '…';

/**
 * Cuts already-parsed Markdown HTML down to at most `limit` visible characters.
 *
 * The cut is made on the parsed DOM rather than on the Markdown source, which is what keeps the
 * result renderable: markers like `**` or `[text](href)` have already become tags, so a cut can
 * never strand half a marker as literal text. An element straddling the cut keeps its tag and its
 * attributes and simply gets shorter text — a link that only partly fits is still a working link.
 */
export function toPreviewHtml(html: string, limit: number): string {
  // DOMParser gives an inert document: no scripts run and no images are fetched while we walk it.
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const body = doc.body;

  // A <br> is invisible once the blocks are flattened onto one line, so keep the break it stood for.
  for (const br of Array.from(body.querySelectorAll('br'))) {
    br.replaceWith(doc.createTextNode(' '));
  }
  // An image can't render on a one-line preview without forcing the row open. Its alt text can.
  for (const img of Array.from(body.querySelectorAll('img'))) {
    const alt = img.getAttribute('alt')?.trim();
    img.replaceWith(...(alt ? [doc.createTextNode(alt)] : []));
  }

  let budget = limit;
  let cut = false;

  const walk = (node: Node): void => {
    for (const child of Array.from(node.childNodes)) {
      if (cut) {
        child.remove();
      } else if (child.nodeType === Node.TEXT_NODE) {
        // Collapse runs of whitespace first: the browser renders them as one space, so counting
        // them raw would spend the budget on characters nobody sees.
        const text = (child.textContent ?? '').replace(/\s+/g, ' ');
        if (text.length <= budget) {
          child.textContent = text;
          budget -= text.length;
        } else {
          child.textContent = clip(text, budget) + ELLIPSIS;
          cut = true;
        }
      } else if (child.nodeType === Node.ELEMENT_NODE) {
        walk(child);
      } else {
        child.remove();
      }
    }
  };
  walk(body);

  return body.innerHTML;
}

/**
 * Cuts `text` to at most `limit` characters, backing up to the last word boundary — but only if
 * that boundary is in the back half, so one long word can't collapse the preview to nothing.
 */
function clip(text: string, limit: number): string {
  const slice = text.slice(0, limit);
  const lastSpace = slice.lastIndexOf(' ');
  return (lastSpace > limit / 2 ? slice.slice(0, lastSpace) : slice).trimEnd();
}
