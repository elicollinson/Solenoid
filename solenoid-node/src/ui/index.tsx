/**
 * UI Entry Point
 *
 * Initializes and renders the terminal-based chat interface using Ink.
 * Connects to the API server via the SOLENOID_SERVER_URL environment variable.
 * Sets up error handlers and waits for user to exit the application.
 *
 * Dependencies:
 * - ink: React for CLIs - builds terminal UIs with React components
 */
import { render } from 'ink';
import { App } from './app.js';
import { uiLogger, setupErrorHandlers } from '../utils/logger.js';

// Set up error handlers to catch crashes
setupErrorHandlers(uiLogger);

uiLogger.info('Starting Solenoid UI');

const serverUrl = process.env['SOLENOID_SERVER_URL'] ?? 'http://localhost:8001';
uiLogger.info({ serverUrl }, 'Connecting to server');

try {
  const instance = render(<App serverUrl={serverUrl} />);
  uiLogger.info('UI rendered successfully');
  await instance.waitUntilExit();
  uiLogger.info('UI exited normally');
} catch (error) {
  const err = error instanceof Error ? error : new Error(String(error));
  uiLogger.fatal({ error: err.message, stack: err.stack }, 'UI crashed');
  process.exit(1);
}
