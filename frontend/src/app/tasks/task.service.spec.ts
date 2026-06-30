import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { TaskService } from './task.service';

describe('TaskService', () => {
  let instance: TaskService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [TaskService, provideHttpClient(), provideHttpClientTesting(), provideRouter([])]
    });
    instance = TestBed.inject(TaskService);
  });

  it('should be created', () => {
    expect(instance).toBeTruthy();
  });
});
