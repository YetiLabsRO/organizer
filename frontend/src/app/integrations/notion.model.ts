/** Shapes returned by the Notion integration API. Tokens are never among them. */

export type NotionStatus = 'active' | 'unprovisioned' | 'needs_reauth' | 'schema_drift';

export interface NotionConnection {
  connected: boolean;
  /** False when the server has no Notion integration credentials configured at all. */
  configured: boolean;
  status?: NotionStatus;
  status_display?: string;
  workspace_name?: string;
  workspace_icon?: string;
  /** Notion does not always issue a refresh token; without one, re-auth will be manual. */
  can_refresh?: boolean;
  last_error?: string;
  connected_at?: string | null;
  last_synced_at?: string | null;

  provisioned?: boolean;
  database_url?: string;
  bootstrap_state?: 'pending' | 'running' | 'done';
  bootstrap_done?: number;
  bootstrap_total?: number;
}

/** A page the user shared with the integration, offered as the database's parent. */
export interface NotionPage {
  id: string;
  title: string;
  url: string;
}
