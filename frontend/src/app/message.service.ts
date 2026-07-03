import { Injectable, signal } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class MessageService {
  readonly messages = signal<string[]>([]);

  add(message: string) {
    this.messages.update(messages => [...messages, message]);
  }

  clear() {
    this.messages.set([]);
  }

  drop(index: number): void {
    this.messages.update(messages => messages.filter((_, i) => i !== index));
  }
}
