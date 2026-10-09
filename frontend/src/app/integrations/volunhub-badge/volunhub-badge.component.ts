import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { REMOVED_REASON_LABELS, VolunHubSource } from '../volunhub.model';

/**
 * Marks a task that came from VolunHub, linking to it there.
 *
 * `compact` is the chip for list rows — labelled "VolunHub" so a task's origin is visible at a
 * glance; the full form is the longer badge for the detail view. A task removed from VolunHub (unassigned, deleted, or the account disconnected) is kept
 * locally and shown with a distinct, muted badge that says why.
 */
@Component({
  selector: 'app-volunhub-badge',
  standalone: true,
  template: `
    @if (source(); as s) {
      @if (compact()) {
        <a class="source-chip" [class.removed]="removed()" [class.has-error]="!removed() && !!s.error"
           [href]="s.url" target="_blank" rel="noopener" [title]="title()" [attr.aria-label]="title()"
           (click)="$event.stopPropagation()">
          <svg class="bi" width="10" height="10" aria-hidden="true">
            <use [attr.xlink:href]="'bootstrap-icons/bootstrap-icons.svg#' + chipIcon()"></use>
          </svg>
          VolunHub
        </a>
      } @else {
        <a class="badge border d-inline-flex align-items-center gap-1 text-decoration-none"
           [class.text-bg-secondary-subtle]="!removed()" [class.text-secondary-emphasis]="!removed()"
           [class.text-bg-warning-subtle]="removed()" [class.text-warning-emphasis]="removed()"
           [href]="s.url" target="_blank" rel="noopener" [title]="title()">
          <svg class="bi" width="12" height="12" role="img" aria-hidden="true">
            <use [attr.xlink:href]="'bootstrap-icons/bootstrap-icons.svg#' + (removed() ? 'x-circle' : 'people-fill')"></use>
          </svg>
          {{ label() }}
        </a>
        @if (s.error) {
          <span class="badge text-bg-warning-subtle text-warning-emphasis border" [title]="s.error">
            Sync problem
          </span>
        }
      }
    }
  `,
  styles: [
    `
      /* List rows: a labelled chip so a task's origin reads at a glance, sized like the status chip. */
      .source-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.3em;
        flex-shrink: 0;
        font-size: 0.68rem;
        font-weight: 600;
        line-height: 1.4;
        padding: 1px 8px;
        border-radius: var(--org-radius-pill);
        /* The -ink tokens are dark text for *tinted* fills; on the dark list background the chip is
           outline-only, so its text uses the light accent itself. */
        border: 1px solid var(--org-info);
        color: var(--org-info);
        background: transparent;
        text-decoration: none;
        white-space: nowrap;
      }
      .source-chip:hover {
        background: var(--org-surface-2);
      }
      .source-chip.has-error {
        border-color: var(--org-warning);
        color: var(--org-warning);
      }
      /* Kept locally but no longer synced: still shows where it came from, visibly detached. */
      .source-chip.removed {
        border-style: dashed;
        border-color: var(--org-border);
        color: var(--org-text-dim);
        text-decoration: line-through;
      }
    `,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VolunHubBadgeComponent {
  readonly source = input<VolunHubSource | null | undefined>(null);
  readonly compact = input(false);

  readonly removed = computed(() => this.source()?.state === 'removed');

  readonly chipIcon = computed(() => {
    if (this.removed()) {
      return 'x-circle';
    }
    return this.source()?.error ? 'exclamation-triangle' : 'people-fill';
  });

  readonly label = computed(() => {
    const source = this.source();
    if (!source) {
      return '';
    }
    if (source.state !== 'removed') {
      return 'Synced with VolunHub';
    }
    const reason = source.removed_reason ? REMOVED_REASON_LABELS[source.removed_reason] : 'no longer synced';
    return `Removed from VolunHub (${reason})`;
  });

  readonly title = computed(() => {
    const source = this.source();
    if (!source) {
      return '';
    }
    if (source.state === 'removed') {
      return `${this.label()}. It is kept here but no longer synced — open it in VolunHub.`;
    }
    return source.error
      ? `Synced with VolunHub — last sync problem: ${source.error}`
      : 'Synced with VolunHub — open it there';
  });
}
