import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { ProjectService } from './project.service';

describe('ProjectService', () => {
  let instance: ProjectService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [ProjectService, provideHttpClient(), provideHttpClientTesting(), provideRouter([])]
    });
    instance = TestBed.inject(ProjectService);
  });

  it('should be created', () => {
    expect(instance).toBeTruthy();
  });
});
