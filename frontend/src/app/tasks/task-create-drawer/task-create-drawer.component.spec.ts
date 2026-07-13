import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { TaskCreateDrawerComponent } from './task-create-drawer.component';

describe('TaskCreateDrawerComponent', () => {
  let component: TaskCreateDrawerComponent;
  let fixture: ComponentFixture<TaskCreateDrawerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TaskCreateDrawerComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    }).compileComponents();

    fixture = TestBed.createComponent(TaskCreateDrawerComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('starts closed with a blank draft defaulting to Normal priority', () => {
    expect(component.open()).toBe(false);
    expect(component.draft.title).toBe('');
    expect(component.draft.priority).toBe(2);
    expect(component.draft.tags).toEqual([]);
  });

  it('close() shuts the drawer', () => {
    component.open.set(true);
    component.close();
    expect(component.open()).toBe(false);
  });
});
