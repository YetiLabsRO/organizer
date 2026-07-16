const ELLIPSIS = '…';

/** Tags that lay out inline, and so are worth keeping in a one-line preview. */
const INLINE_TAGS = new Set([
  'A', 'ABBR', 'B', 'CITE', 'CODE', 'DEL', 'EM', 'I', 'INS', 'KBD', 'MARK', 'Q', 'S', 'SAMP',
  'SMALL', 'SPAN', 'STRONG', 'SUB', 'SUP', 'TIME', 'U', 'VAR',
]);

/**
 * Reduces already-parsed Markdown HTML to a single line of at most `limit` visible characters.
 *
 * Both halves of that — the flattening and the cut — are done here on the parsed DOM rather than
 * in CSS or on the Markdown source, and for different reasons.
 *
 * The flattening can't be CSS: Angular's emulated encapsulation compiles a descendant rule to
 * `.markdown-body[_ngcontent-x] p[_ngcontent-x]`, and nodes injected through `[innerHTML]` never
 * carry that attribute, so no reset here can reach them. Dropping the block tags outright does it.
 *
 * The cut can't be on the Markdown source: markers like `**` or `[text](href)` would be left half
 * open and render as literal text. Cutting the parsed tree means every marker has already become a
 * tag, and an element straddling the cut keeps its tag and attributes with only its text shortened
 * — a link that only partly fits is still a working link.
 */
export function toPreviewHtml(html: string, limit: number): string {
  // DOMParser gives an inert document: no scripts run and no images are fetched while we walk it.
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const preview = doc.createElement('div');

  flatten(doc.body, preview, doc);
  collapseWhitespace(preview);
  truncate(preview, limit);

  return preview.innerHTML;
}

/** Rebuilds `source`'s content under `target` using inline tags and text only. */
function flatten(source: Node, target: Element, doc: Document): void {
  for (const child of Array.from(source.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) {
      target.append(doc.createTextNode(child.textContent ?? ''));
      continue;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) {
      continue;
    }

    const el = child as Element;
    if (el.tagName === 'BR') {
      // Flattened onto one line a <br> has nothing to break, but the word gap it stood for reads.
      target.append(' ');
    } else if (el.tagName === 'IMG') {
      // An image can't render on a one-line row without forcing it open. Its alt text can.
      const alt = el.getAttribute('alt')?.trim();
      if (alt) {
        target.append(alt);
      }
    } else if (INLINE_TAGS.has(el.tagName)) {
      const clone = el.cloneNode(false) as Element;
      flatten(el, clone, doc);
      target.append(clone);
    } else {
      // A block: keep the text, drop the box, and leave a gap so its words stay separate words.
      target.append(' ');
      flatten(el, target, doc);
      target.append(' ');
    }
  }
}

/**
 * Squeezes whitespace runs down to single spaces across the whole tree, so that the budget below
 * is spent on characters a reader actually sees.
 */
function collapseWhitespace(root: Element): void {
  const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: Text[] = [];
  while (walker.nextNode()) {
    texts.push(walker.currentNode as Text);
  }

  let afterSpace = true; // Leading whitespace has nothing to separate, so it goes.
  for (const node of texts) {
    let text = (node.textContent ?? '').replace(/\s+/g, ' ');
    if (afterSpace && text.startsWith(' ')) {
      text = text.slice(1);
    }
    if (text) {
      afterSpace = text.endsWith(' ');
    }
    node.textContent = text;
  }

  for (let i = texts.length - 1; i >= 0; i--) {
    const trimmed = (texts[i].textContent ?? '').replace(/\s+$/, '');
    texts[i].textContent = trimmed;
    if (trimmed) {
      break;
    }
  }

  for (const node of texts) {
    if (!node.textContent) {
      node.remove();
    }
  }
}

/** Spends `limit` characters over the tree in document order, then drops the rest. */
function truncate(root: Element, limit: number): void {
  let budget = limit;
  let cut = false;
  let ellipsised = false;

  const walk = (node: Node): void => {
    for (const child of Array.from(node.childNodes)) {
      if (cut) {
        child.remove();
      } else if (child.nodeType === Node.TEXT_NODE) {
        const text = child.textContent ?? '';
        if (text.length <= budget) {
          budget -= text.length;
        } else {
          const kept = clip(text, budget);
          cut = true;
          if (kept) {
            child.textContent = kept + ELLIPSIS;
            ellipsised = true;
          } else {
            // The budget ran out right where this text began. An ellipsis here would be the whole
            // of its element — a link reading only "…" — so drop it and trail the ellipsis below.
            child.remove();
          }
        }
      } else {
        walk(child);
      }
    }
  };
  walk(root);

  if (cut && !ellipsised) {
    for (const el of Array.from(root.querySelectorAll('*'))) {
      if (!el.textContent) {
        el.remove();
      }
    }
    const tail = lastTextNode(root);
    if (tail) {
      tail.textContent = (tail.textContent ?? '').replace(/\s+$/, '');
    }
    root.append(ELLIPSIS);
  }
}

function lastTextNode(root: Element): Text | null {
  const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let last: Text | null = null;
  while (walker.nextNode()) {
    last = walker.currentNode as Text;
  }
  return last;
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
