/**
 * EDT Runtime Configuration
 * Centralized config for API endpoints and environment settings.
 * IMPORTANT: window.RUNTIME_CONFIG is the primary contract read by app.js,
 *            config.html, and monitor.html. Do not remove it.
 */
window.RUNTIME_CONFIG = {
  WS_URL: 'ws://127.0.0.1:18765',
  API_BASE: 'http://127.0.0.1:18787',
  AUTH_TOKEN: 'edt-local-dev-token'
};

window.EDT_CONFIG = {
  // API_ROOT: '/api', // Uncomment for production API integration
  VERSION: '2.1.0',
  ENV: 'DEVELOPMENT'
};
