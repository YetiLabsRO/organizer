import { defineConfig } from 'vitest/config';

// Loaded by the @angular/build:unit-test builder via `test.runnerConfig` in angular.json. The
// builder still owns the environment (jsdom) and file discovery — this only widens timeouts, so
// keep it to that and nothing that would fight the builder's own setup.
//
// Why: component smoke tests create a TestBed, which takes ~400ms on an idle machine but can blow
// past Vitest's 5s default when CI (or several dev servers) saturates the box. That is a load
// artefact, not a hung test, so raise the ceiling rather than let it flake.
export default defineConfig({
  test: {
    testTimeout: 20000,
    hookTimeout: 20000,
  },
});
