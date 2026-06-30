import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { SlicePipe } from '@angular/common';

import { MessageService } from '../message.service';

@Component({
  selector: 'app-messages',
  imports: [SlicePipe],
  templateUrl: './messages.component.html',
  styleUrls: ['./messages.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MessagesComponent {
  readonly messageService = inject(MessageService);
}
