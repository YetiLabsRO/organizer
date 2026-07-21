export const environment = {
  production: true,
  // Same-origin in production (served behind the Django/host domain).
  apiBase: '',
  // Empty → the live-sync socket URL is derived from `location` (wss:// on HTTPS), so it follows the
  // deployment's own host without hardcoding it. See TaskEventsService.
  wsBase: ''
};
