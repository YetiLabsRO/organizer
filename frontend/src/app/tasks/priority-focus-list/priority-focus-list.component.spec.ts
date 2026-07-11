import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { PriorityFocusListComponent } from './priority-focus-list.component';

describe('PriorityFocusListComponent', () => {
  let component: PriorityFocusListComponent;
  let fixture: ComponentFixture<PriorityFocusListComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PriorityFocusListComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), provideNoopAnimations()],
    }).compileComponents();
  });

  beforeEach(() => {
    fixture = TestBed.createComponent(PriorityFocusListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('renders the four priority bands', () => {
    const titles = Array.from(fixture.nativeElement.querySelectorAll('.band-title')).map(
      (el) => (el as HTMLElement).textContent?.trim(),
    );
    expect(titles).toEqual(['Urgent & Overdue', 'High Priority', 'Normal', 'Low Priority']);
  });

  it('starts on the Todo view', () => {
    expect(component.viewMode()).toBe('todo');
  });
});
