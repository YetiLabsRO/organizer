import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { Project } from '../../projects/project';
import { ProjectService } from '../../projects/project.service';
import { VolunHubConnection, VolunHubProjectLink } from '../volunhub.model';
import { VolunHubService } from '../volunhub.service';

/**
 * Connect VolunHub, see how the sync is doing, and map VolunHub projects onto local ones.
 *
 * VolunHub projects are auto-created here the first time a task from one arrives; the mapping
 * table lets the user fold such a project into one they already had. The disclosure list carries
 * the behaviours nobody could guess from the UI: only *assigned* tasks come in, nothing is ever
 * created or deleted in VolunHub, and every edit pushed there notifies the task's watchers.
 */
@Component({
  selector: 'app-volunhub-settings',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './volunhub-settings.component.html',
  styleUrls: ['../notion-settings/notion-settings.component.css', './volunhub-settings.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VolunHubSettingsComponent {
  private readonly volunhub = inject(VolunHubService);
  private readonly projectService = inject(ProjectService);
  private readonly route = inject(ActivatedRoute);

  readonly connection = signal<VolunHubConnection | null>(null);
  readonly projectLinks = signal<VolunHubProjectLink[]>([]);
  readonly localProjects = signal<Project[]>([]);

  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly notice = signal('');

  readonly connected = computed(() => this.connection()?.connected === true);
  readonly configured = computed(() => this.connection()?.configured !== false);
  readonly needsReauth = computed(() => this.connection()?.status === 'needs_reauth');
  readonly readOnly = computed(() => this.connected() && this.connection()?.can_write === false);
  readonly contentPushDisabled = computed(
    () => this.connected() && !this.readOnly() && this.connection()?.content_push_enabled === false,
  );

  constructor() {
    // The OAuth callback bounces back here with its outcome in the query string.
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      const outcome = params.get('volunhub');
      if (outcome === 'connected') {
        this.notice.set('VolunHub connected. Your assigned tasks are being imported now.');
      } else if (outcome === 'error') {
        this.error.set(this.describeCallbackError(params.get('reason')));
      }
    });
    this.refresh();
  }

  private describeCallbackError(reason: string | null): string {
    switch (reason) {
      case 'access_denied':
        return 'You declined access in VolunHub, so nothing was connected.';
      case 'invalid_state':
        return 'That authorization link had expired or was already used. Please try connecting again.';
      case 'insufficient_scope':
        return 'VolunHub did not grant access to read your tasks, so nothing was connected.';
      case 'missing_code':
        return 'VolunHub did not return an authorization code. Please try again.';
      case 'exchange_failed':
        return 'VolunHub rejected the authorization. Please try connecting again.';
      default:
        return 'Connecting to VolunHub failed. Please try again.';
    }
  }

  refresh(): void {
    this.loading.set(true);
    this.volunhub.status().subscribe({
      next: (state) => {
        this.connection.set(state);
        this.loading.set(false);
        if (state.connected) {
          this.loadProjects();
        }
      },
      error: () => {
        this.error.set('Could not load the VolunHub connection.');
        this.loading.set(false);
      },
    });
  }

  loadProjects(): void {
    this.volunhub.projects().subscribe({
      next: (links) => this.projectLinks.set(links),
      error: () => this.error.set('Could not list your VolunHub projects.'),
    });
    this.projectService.getProjects().subscribe((projects) => this.localProjects.set(projects));
  }

  connect(): void {
    this.busy.set(true);
    this.error.set('');
    this.volunhub.connect().subscribe({
      next: ({ authorize_url }) => {
        // A full navigation, not an XHR: the user has to log in to VolunHub and approve.
        window.location.href = authorize_url;
      },
      error: (response) => {
        this.error.set(response?.error?.detail ?? 'Could not start the VolunHub authorization.');
        this.busy.set(false);
      },
    });
  }

  disconnect(): void {
    this.busy.set(true);
    this.volunhub.disconnect().subscribe({
      next: (state) => {
        this.connection.set(state);
        this.projectLinks.set([]);
        this.busy.set(false);
        this.notice.set(
          'Disconnected. Your VolunHub tasks stay here, marked as disconnected; reconnecting picks them up again.',
        );
      },
      error: () => {
        this.error.set('Could not disconnect.');
        this.busy.set(false);
      },
    });
  }

  syncNow(retryContent = false): void {
    this.busy.set(true);
    this.volunhub.sync(retryContent).subscribe({
      next: () => {
        this.busy.set(false);
        this.notice.set(retryContent ? 'Content edits re-enabled; sync queued.' : 'Sync queued.');
        if (retryContent) {
          this.refresh();
        }
      },
      error: (response) => {
        this.error.set(response?.error?.detail ?? 'Could not queue a sync.');
        this.busy.set(false);
      },
    });
  }

  merge(link: VolunHubProjectLink, event: Event): void {
    const projectId = Number((event.target as HTMLSelectElement).value);
    if (!projectId || projectId === link.project_id) {
      return;
    }
    this.busy.set(true);
    this.volunhub.mergeProject(link.external_id, projectId).subscribe({
      next: (updated) => {
        this.projectLinks.update((links) => links.map((l) => (l.external_id === updated.external_id ? updated : l)));
        this.projectService.invalidateProjectsCache();
        this.projectService.getProjects().subscribe((projects) => this.localProjects.set(projects));
        this.busy.set(false);
        this.notice.set(`"${link.external_name}" now maps to "${updated.project_title}".`);
      },
      error: () => {
        this.error.set('Could not merge the project.');
        this.busy.set(false);
      },
    });
  }
}
