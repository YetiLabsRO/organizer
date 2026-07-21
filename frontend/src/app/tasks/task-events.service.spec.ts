import { ApplicationRef, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthService } from '../auth.service';
import { TaskEvent, TaskEventsService, SocketLike } from './task-events.service';

/** A fake WebSocket the test drives by hand (open / message / server-close). */
class FakeSocket implements SocketLike {
  sent: string[] = [];
  readyState = 0; // CONNECTING
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;

  send(data: string): void {
    this.sent.push(data);
  }
  close(): void {
    this.readyState = 3; // CLOSED
  }

  // --- test drivers ---
  open(): void {
    this.readyState = 1; // OPEN
    this.onopen?.({});
  }
  message(obj: unknown): void {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
  serverClose(code: number): void {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

class FakeAuth {
  loggedIn = signal(false);
  private token: string | null = 'tok-123';
  getUserToken(): string | null {
    return this.token;
  }
  setToken(t: string | null): void {
    this.token = t;
  }
}

describe('TaskEventsService', () => {
  let service: TaskEventsService;
  let auth: FakeAuth;
  let sockets: FakeSocket[];
  const flush = () => TestBed.inject(ApplicationRef).tick();
  const latest = () => sockets[sockets.length - 1];

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        TaskEventsService,
        { provide: AuthService, useClass: FakeAuth as unknown as typeof AuthService },
      ],
    });
    service = TestBed.inject(TaskEventsService);
    auth = TestBed.inject(AuthService) as unknown as FakeAuth;

    sockets = [];
    service.socketFactory = () => {
      const s = new FakeSocket();
      sockets.push(s);
      return s;
    };
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** Log in and reach the authenticated (auth.ok) state on a fresh fake socket. */
  function authenticate(): FakeSocket {
    auth.loggedIn.set(true);
    flush();
    const socket = latest();
    socket.open();
    socket.message({ type: 'auth.ok' });
    return socket;
  }

  it('sends the auth frame as its first message on open', () => {
    auth.loggedIn.set(true);
    flush();
    expect(sockets.length).toBe(1);

    latest().open();

    expect(JSON.parse(latest().sent[0])).toEqual({ type: 'auth', token: 'tok-123' });
  });

  it('marks itself connected after auth.ok', () => {
    expect(service.connected()).toBe(false);
    authenticate();
    expect(service.connected()).toBe(true);
  });

  it('forwards task events but drops ones not newer than what it has applied', () => {
    const socket = authenticate();
    const seen: TaskEvent[] = [];
    service.events$.subscribe((e) => seen.push(e));

    socket.message({ type: 'task.updated', id: 1, task: { changed_date: '2026-01-01T10:00:00Z' } });
    socket.message({ type: 'task.updated', id: 1, task: { changed_date: '2026-01-01T09:00:00Z' } }); // stale
    socket.message({ type: 'task.updated', id: 1, task: { changed_date: '2026-01-01T11:00:00Z' } }); // newer

    expect(seen.map((e) => e.type)).toEqual(['task.updated', 'task.updated']);
    const kept = seen[1] as unknown as { task: { changed_date: string } };
    expect(kept.task.changed_date).toBe('2026-01-01T11:00:00Z');
  });

  it('always forwards deletes', () => {
    const socket = authenticate();
    const seen: TaskEvent[] = [];
    service.events$.subscribe((e) => seen.push(e));

    socket.message({ type: 'task.deleted', id: 5 });

    expect(seen).toEqual([{ type: 'task.deleted', id: 5 }]);
  });

  it('reconnects with backoff after an unexpected close', () => {
    vi.useFakeTimers();
    authenticate();
    expect(sockets.length).toBe(1);

    latest().serverClose(1006); // abnormal closure
    vi.advanceTimersByTime(2_000); // past the ~1s (+jitter) first backoff

    expect(sockets.length).toBe(2);
  });

  it('does not reconnect after a 4401 (auth failed) close', () => {
    vi.useFakeTimers();
    authenticate();

    latest().serverClose(4401);
    vi.advanceTimersByTime(60_000);

    expect(sockets.length).toBe(1); // no new socket
  });

  it('closes the socket and stops on logout, without reconnecting', () => {
    vi.useFakeTimers();
    const socket = authenticate();
    expect(service.connected()).toBe(true);

    auth.loggedIn.set(false);
    flush();

    expect(socket.readyState).toBe(3); // CLOSED
    expect(service.connected()).toBe(false);
    vi.advanceTimersByTime(60_000);
    expect(sockets.length).toBe(1); // no reconnect after an intentional close
  });

  it('emits a reconnected event only on a *re*connection, not the first', () => {
    vi.useFakeTimers();
    const events: TaskEvent[] = [];
    service.events$.subscribe((e) => events.push(e));

    const first = authenticate(); // first connection — no "reconnected"
    expect(events.filter((e) => e.type === 'reconnected')).toHaveLength(0);

    first.serverClose(1006);
    vi.advanceTimersByTime(2_000);
    latest().open();
    latest().message({ type: 'auth.ok' }); // second connection

    expect(events.filter((e) => e.type === 'reconnected')).toHaveLength(1);
  });
});
