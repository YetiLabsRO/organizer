import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { REMOVED_REASON_LABELS, VolunHubSource } from '../volunhub.model';

/**
 * Marks a task that came from VolunHub, linking to it there.
 *
 * `compact` is the icon-only form for list rows; the full form is a labelled badge for the detail
 * view. A task removed from VolunHub (unassigned, deleted, or the account disconnected) is kept
 * locally and shown with a distinct, muted badge that says why.
 */
@Component({
  selector: 'app-volunhub-badge',
  standalone: true,
  template: `
    @if (source(); as s) {
      @if (compact()) {
        <a class="lh-1" [class.text-secondary]="!removed()" [class.text-warning]="removed()"
           [href]="s.url" target="_blank" rel="noopener" [title]="title()" [attr.aria-label]="title()"
           (click)="$event.stopPropagation()">
          <svg class="bi" width="12" height="12" role="img">
            <use [attr.xlink:href]="'bootstrap-icons/bootstrap-icons.svg#' + (removed() ? 'x-circle' : 'people-fill')"></use>
          </svg>
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
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VolunHubBadgeComponent {
  readonly source = input<VolunHubSource | null | undefined>(null);
  readonly compact = input(false);

  readonly removed = computed(() => this.source()?.state === 'removed');

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
