import { Injectable, effect, inject, signal } from '@angular/core';
import { Subject } from 'rxjs';

import { environment } from '../../environments/environment';
import { AuthService } from '../auth.service';
import { Task } from './task';

/** The task shape the server sends — the list serializer's fields, without the client-only `_tags`. */
export type ServerTask = Omit<Task, '_tags'>;

/** Events pushed from the server over the live-sync socket, plus a synthetic reconnect signal. */
export type TaskEvent =
  | { type: 'task.created'; id: number; task: ServerTask }
  | { type: 'task.updated'; id: number; task: ServerTask }
  | { type: 'task.deleted'; id: number }
  /** Emitted after the socket re-establishes following a drop, so views can refetch what they missed. */
  | { type: 'reconnected' };

/** Minimal WebSocket surface, so tests can inject a fake without a real socket. */
export interface SocketLike {
  send(data: string): void;
  close(): void;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: { code: number }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
  readyState: number;
}

// WebSocket.readyState values, as literals so this module never touches the global `WebSocket`
// (which may be absent under jsdom in unit tests).
const WS_CONNECTING = 0;
const WS_OPEN = 1;

const HEARTBEAT_MS = 25_000;
const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;
/** Application close code the server sends when auth is missing/invalid — do not reconnect on it. */
const AUTH_FAILED_CODE = 4401;

/**
 * Keeps a single WebSocket to `/ws/tasks/` open while the user is authenticated and surfaces task
 * changes made anywhere (other tabs, the phone, an MCP client, the recurring-task job) as an event
 * stream the task views subscribe to.
 *
 * The DRF token cannot ride a WebSocket handshake header, so the socket authenticates by sending
 * `{type:'auth', token}` as its first frame. The connection self-heals with exponential backoff;
 * a `4401` close (bad credentials) is treated as fatal so we don't hammer the server in a loop.
 */
@Injectable({ providedIn: 'root' })
export class TaskEventsService {
  private readonly auth = inject(AuthService);

  /** True while an authenticated socket is open. */
  readonly connected = signal(false);

  private readonly eventsSubject = new Subject<TaskEvent>();
  readonly events$ = this.eventsSubject.asObservable();

  /** Overridable in tests; production opens a real browser WebSocket. */
  socketFactory: (url: string) => SocketLike = (url) => new WebSocket(url) as unknown as SocketLike;

  private socket: SocketLike | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  /** Set on a 4401 close so we stop reconnecting until the next login. */
  private authFailed = false;
  /** Distinguishes an intentional teardown (logout) from a dropped connection. */
  private closingIntentionally = false;
  /** True once we've had at least one live connection, so a later open counts as a *re*connect. */
  private hadConnection = false;

  /** Last-seen `changed_date` (ms) per task id — drops stale/out-of-order events. */
  private readonly lastChangedAt = new Map<number, number>();

  constructor() {
    // Follow auth state: connect when logged in, tear the socket down when logged out.
    effect(() => {
      if (this.auth.loggedIn()) {
        this.authFailed = false;
        this.connect();
      } else {
        this.teardown();
      }
    });
  }

  private wsUrl(): string {
    const base = environment.wsBase;
    if (base) {
      return `${base}/ws/tasks/`;
    }
    // Same-origin (prod): follow the page's own scheme/host.
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${scheme}://${location.host}/ws/tasks/`;
  }

  private connect(): void {
    if (this.authFailed) {
      return;
    }
    if (this.socket && (this.socket.readyState === WS_OPEN || this.socket.readyState === WS_CONNECTING)) {
      return;
    }
    const token = this.auth.getUserToken();
    if (!token) {
      return;
    }
    this.clearReconnectTimer();
    this.closingIntentionally = false;

    const socket = this.socketFactory(this.wsUrl());
    this.socket = socket;
    socket.onopen = () => socket.send(JSON.stringify({ type: 'auth', token }));
    socket.onmessage = (ev) => this.onMessage(ev.data);
    socket.onclose = (ev) => this.onClose(ev.code);
    socket.onerror = () => {
      /* A close event always follows; reconnection is handled there. */
    };
  }

  private onMessage(data: unknown): void {
    let msg: { type?: string; id?: number; task?: Task };
    try {
      msg = JSON.parse(String(data));
    } catch {
      return;
    }
    switch (msg.type) {
      case 'auth.ok':
        this.connected.set(true);
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        // A reconnect (not the first connect) may have missed events while down — tell views to refetch.
        if (this.hadConnection) {
          this.eventsSubject.next({ type: 'reconnected' });
        }
        this.hadConnection = true;
        return;
      case 'pong':
        return;
      case 'task.created':
      case 'task.updated':
      case 'task.deleted':
        if (typeof msg.id !== 'number' || this.isStale(msg)) {
          return;
        }
        this.eventsSubject.next(msg as TaskEvent);
        return;
    }
  }

  /** Drop an event that isn't strictly newer than what we've already applied for that task. */
  private isStale(msg: { type?: string; id?: number; task?: Task }): boolean {
    const id = msg.id as number;
    if (msg.type === 'task.deleted') {
      this.lastChangedAt.delete(id);
      return false; // deletes always apply
    }
    const raw = msg.task?.changed_date;
    const changed = raw ? Date.parse(String(raw)) : NaN;
    if (Number.isNaN(changed)) {
      return false; // nothing to compare against — let it through
    }
    const prev = this.lastChangedAt.get(id);
    if (prev !== undefined && changed <= prev) {
      return true;
    }
    this.lastChangedAt.set(id, changed);
    return false;
  }

  private onClose(code: number): void {
    this.connected.set(false);
    this.stopHeartbeat();
    this.socket = null;
    if (this.closingIntentionally) {
      return;
    }
    if (code === AUTH_FAILED_CODE) {
      // Credentials rejected: reconnecting would just loop. Wait for a fresh login.
      this.authFailed = true;
      return;
    }
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (!this.auth.loggedIn() || this.authFailed) {
      return;
    }
    const backoff = Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** this.reconnectAttempts);
    const delay = backoff + Math.random() * 0.3 * backoff; // jitter, so many clients don't sync up
    this.reconnectAttempts++;
    this.clearReconnectTimer();
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.socket?.readyState === WS_OPEN) {
        this.socket.send(JSON.stringify({ type: 'ping' }));
      }
    }, HEARTBEAT_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  /** Intentional shutdown on logout: close the socket and forget all per-session state. */
  private teardown(): void {
    this.closingIntentionally = true;
    this.clearReconnectTimer();
    this.stopHeartbeat();
    this.reconnectAttempts = 0;
    this.hadConnection = false;
    this.lastChangedAt.clear();
    this.connected.set(false);
    if (this.socket) {
      this.socket.onclose = null; // don't let close() schedule a reconnect
      this.socket.close();
      this.socket = null;
    }
  }
}
