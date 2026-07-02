import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { AuthService } from '../auth.service';

export const tokenInterceptor: HttpInterceptorFn = (request, next) => {
  const authToken = inject(AuthService).getUserToken();

  // No auth token: pass the request through unchanged.
  if (!authToken) {
    return next(request);
  }

  const authRequest = request.clone({
    headers: request.headers.set('Authorization', `Token ${authToken}`),
  });

  return next(authRequest);
};
