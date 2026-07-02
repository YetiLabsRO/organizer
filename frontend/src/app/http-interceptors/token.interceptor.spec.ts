import { tokenInterceptor } from './token.interceptor';

describe('tokenInterceptor', () => {
  it('is a functional interceptor', () => {
    expect(typeof tokenInterceptor).toBe('function');
  });
});
