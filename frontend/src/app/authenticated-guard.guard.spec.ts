import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { AuthenticatedGuard } from './authenticated-guard.service';

describe('AuthenticatedGuard', () => {
  let instance: AuthenticatedGuard;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [AuthenticatedGuard, provideHttpClient(), provideHttpClientTesting(), provideRouter([])]
    });
    instance = TestBed.inject(AuthenticatedGuard);
  });

  it('should be created', () => {
    expect(instance).toBeTruthy();
  });
});
