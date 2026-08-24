import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { NotionConnection, NotionPage } from '../notion.model';
import { NotionService } from '../notion.service';

/**
 * Connect Notion, choose where the task database goes, and watch the first upload run.
 *
 * The screen also carries the disclosure copy for the three behaviours that would otherwise
 * surprise someone: the page body is never synced, deletion is symmetric, and projects/tags typed
 * in Notion are matched against existing ones rather than created.
 */
@Component({
  selector: 'app-notion-settings',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './notion-settings.component.html',
  styleUrls: ['./notion-settings.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NotionSettingsComponent {
  private readonly notion = inject(NotionService);
  private readonly route = inject(ActivatedRoute);

  readonly connection = signal<NotionConnection | null>(null);
  readonly pages = signal<NotionPage[]>([]);
  readonly selectedPageId = signal<string>('');

  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly notice = signal('');

  readonly connected = computed(() => this.connection()?.connected === true);
  readonly configured = computed(() => this.connection()?.configured !== false);
  readonly provisioned = computed(() => this.connection()?.provisioned === true);
  readonly status = computed(() => this.connection()?.status ?? null);
  readonly needsReauth = computed(() => this.status() === 'needs_reauth');
  readonly schemaDrift = computed(() => this.status() === 'schema_drift');
  readonly bootstrapping = computed(() => this.connection()?.bootstrap_state === 'running');

  readonly bootstrapPercent = computed(() => {
    const state = this.connection();
    if (!state?.bootstrap_total) {
      return 0;
    }
    return Math.min(100, Math.round(((state.bootstrap_done ?? 0) / state.bootstrap_total) * 100));
  });

  constructor() {
    // The OAuth callback bounces back here with a result in the query string, because it is a
    // browser navigation and cannot return anything to the SPA directly.
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      const outcome = params.get('notion');
      if (outcome === 'connected') {
        this.notice.set('Notion connected. Choose where the task database should live.');
      } else if (outcome === 'error') {
        this.error.set(this.describeCallbackError(params.get('reason')));
      }
    });
    this.refresh();
  }

  private describeCallbackError(reason: string | null): string {
    switch (reason) {
      case 'access_denied':
        return 'You declined access in Notion, so nothing was connected.';
      case 'invalid_state':
        return 'That authorization link had expired or was already used. Please try connecting again.';
      case 'missing_code':
        return 'Notion did not return an authorization code. Please try again.';
      case 'exchange_failed':
        return 'Notion rejected the authorization. Please try connecting again.';
      default:
        return 'Connecting to Notion failed. Please try again.';
    }
  }

  refresh(): void {
    this.loading.set(true);
    this.notion.status().subscribe({
      next: (state) => {
        this.connection.set(state);
        this.loading.set(false);
        if (state.connected && !state.provisioned) {
          this.loadPages();
        }
      },
      error: () => {
        this.error.set('Could not load the Notion connection.');
        this.loading.set(false);
      },
    });
  }

  connect(): void {
    this.busy.set(true);
    this.error.set('');
    this.notion.connect().subscribe({
      next: ({ authorize_url }) => {
        // A full navigation, not an XHR: the user must see Notion's consent screen and pick pages.
        window.location.href = authorize_url;
      },
      error: () => {
        this.error.set('Could not start the Notion authorization.');
        this.busy.set(false);
      },
    });
  }

  disconnect(): void {
    this.busy.set(true);
    this.notion.disconnect().subscribe({
      next: (state) => {
        this.connection.set(state);
        this.pages.set([]);
        this.busy.set(false);
        // Notion has no revocation endpoint, so the user has to finish the job themselves.
        this.notice.set(
          'Disconnected. To fully revoke access, also remove Organizer from your Notion settings ' +
            '(Settings → Connections).',
        );
      },
      error: () => {
        this.error.set('Could not disconnect.');
        this.busy.set(false);
      },
    });
  }

  loadPages(): void {
    this.notion.pages().subscribe({
      next: (pages) => {
        this.pages.set(pages);
        if (pages.length && !this.selectedPageId()) {
          this.selectedPageId.set(pages[0].id);
        }
      },
      error: () => this.error.set('Could not list your Notion pages.'),
    });
  }

  selectPage(event: Event): void {
    this.selectedPageId.set((event.target as HTMLSelectElement).value);
  }

  provision(): void {
    const parent = this.selectedPageId();
    if (!parent) {
      return;
    }
    this.busy.set(true);
    this.error.set('');
    this.notion.provision(parent).subscribe({
      next: (state) => {
        this.connection.set(state);
        this.busy.set(false);
        this.notice.set('Database created. Your existing tasks are being uploaded now.');
      },
      error: (response) => {
        this.error.set(response?.error?.detail ?? 'Could not create the Notion database.');
        this.busy.set(false);
      },
    });
  }

  syncNow(full = false): void {
    this.busy.set(true);
    this.notion.sync(full).subscribe({
      next: () => {
        this.busy.set(false);
        this.notice.set('Sync queued.');
      },
      error: () => {
        this.error.set('Could not queue a sync.');
        this.busy.set(false);
      },
    });
  }
}
