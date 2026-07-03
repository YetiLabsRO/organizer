import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { TagService } from './tag.service';

describe('TagService', () => {
  let instance: TagService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [TagService, provideHttpClient(), provideHttpClientTesting(), provideRouter([])]
    });
    instance = TestBed.inject(TagService);
  });

  it('should be created', () => {
    expect(instance).toBeTruthy();
  });
});
