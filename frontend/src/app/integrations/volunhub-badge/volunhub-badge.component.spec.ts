import { TestBed } from '@angular/core/testing';

import { VolunHubBadgeComponent } from './volunhub-badge.component';

describe('VolunHubBadgeComponent', () => {
  function render(source: unknown, compact = false): HTMLElement {
    const fixture = TestBed.createComponent(VolunHubBadgeComponent);
    fixture.componentRef.setInput('source', source);
    fixture.componentRef.setInput('compact', compact);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders nothing for a task that did not come from VolunHub', () => {
    expect(render(null).textContent?.trim()).toBe('');
  });

  it('links a synced task to VolunHub', () => {
    const element = render({ url: 'https://vh/proiecte/task-uri/5/', state: 'active', removed_reason: null, error: null });
    const link = element.querySelector('a')!;
    expect(link.getAttribute('href')).toBe('https://vh/proiecte/task-uri/5/');
    expect(link.textContent).toContain('Synced with VolunHub');
  });

  it('says why a removed task is no longer synced', () => {
    const element = render({ url: 'https://vh/x/', state: 'removed', removed_reason: 'unassigned', error: null });
    expect(element.textContent).toContain('Removed from VolunHub (unassigned from you)');
  });

  it('is icon-only when compact, with the label as its accessible name', () => {
    const element = render({ url: 'https://vh/x/', state: 'removed', removed_reason: 'deleted', error: null }, true);
    const link = element.querySelector('a')!;
    expect(link.textContent?.trim()).toBe('');
    expect(link.getAttribute('aria-label')).toContain('deleted in VolunHub');
  });
});
