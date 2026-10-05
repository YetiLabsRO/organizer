import { ChangeDetectionStrategy, Component } from '@angular/core';

import { NotionSettingsComponent } from '../notion-settings/notion-settings.component';
import { VolunHubSettingsComponent } from '../volunhub-settings/volunhub-settings.component';

/** `/settings/integrations`: one card per external service. OAuth callbacks return here. */
@Component({
  selector: 'app-integrations-page',
  standalone: true,
  imports: [NotionSettingsComponent, VolunHubSettingsComponent],
  template: `
    <div class="container-fluid py-3">
      <h1 class="h3 mb-3">Integrations</h1>
      <app-notion-settings />
      <app-volunhub-settings />
    </div>
  `,
  styles: [':host h1 { font-family: var(--org-font-heading); font-weight: 700; }'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class IntegrationsPageComponent {}
