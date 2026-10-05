/** Shapes returned by the VolunHub integration API. Tokens are never among them. */

export type VolunHubStatus = 'active' | 'needs_reauth';

export interface VolunHubConnection {
  connected: boolean;
  /** False when the server has VolunHub sync disabled (no base URL). */
  configured: boolean;
  base_url: string;
  status?: VolunHubStatus;
  status_display?: string;
  /** False when the user unticked "change your task status" on VolunHub's consent screen. */
  can_write?: boolean;
  /** False once VolunHub refused a content update; status changes still flow. */
  content_push_enabled?: boolean;
  last_error?: string;
  connected_at?: string | null;
  last_synced_at?: string | null;
  linked_tasks?: number;
  removed_tasks?: number;
  task_errors?: number;
}

/** A VolunHub project the user's tasks came from, and the local project it maps to. */
export interface VolunHubProjectLink {
  external_id: number;
  external_name: string;
  external_slug: string;
  /** True while it maps to the project the sync created; false once merged into another. */
  auto_created: boolean;
  project_id: number | null;
  project_title: string | null;
}

/** The `volunhub` field on a task: present when the task came from VolunHub. */
export interface VolunHubSource {
  url: string;
  state: 'active' | 'removed';
  removed_reason: 'unassigned' | 'deleted' | 'disconnected' | null;
  error: string | null;
}

export const REMOVED_REASON_LABELS: Record<NonNullable<VolunHubSource['removed_reason']>, string> = {
  unassigned: 'unassigned from you',
  deleted: 'deleted in VolunHub',
  disconnected: 'VolunHub disconnected',
};
