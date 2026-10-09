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

  it('shows a labelled VolunHub chip in list rows', () => {
    const element = render({ url: 'https://vh/x/', state: 'active', removed_reason: null, error: null }, true);
    const chip = element.querySelector('a.source-chip')!;
    expect(chip.textContent?.trim()).toBe('VolunHub');
    expect(chip.classList).not.toContain('removed');
  });

  it('keeps the chip for a removed task but marks it detached, with the reason as its name', () => {
    const element = render({ url: 'https://vh/x/', state: 'removed', removed_reason: 'deleted', error: null }, true);
    const chip = element.querySelector('a.source-chip')!;
    expect(chip.textContent?.trim()).toBe('VolunHub');
    expect(chip.classList).toContain('removed');
    expect(chip.getAttribute('aria-label')).toContain('deleted in VolunHub');
  });

  it('flags a sync problem on the chip', () => {
    const element = render({ url: 'https://vh/x/', state: 'active', removed_reason: null, error: '409' }, true);
    expect(element.querySelector('a.source-chip')!.classList).toContain('has-error');
  });
});
