/**
 * UI Entry Point
 *
 * Initializes and renders the terminal-based chat interface using Ink.
 * Agent initialization happens within the App component with a loading screen.
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

try {
  const instance = render(<App />);
  uiLogger.info('UI rendered successfully');
  await instance.waitUntilExit();
  uiLogger.info('UI exited normally');
} catch (error) {
  const err = error instanceof Error ? error : new Error(String(error));
  uiLogger.fatal({ error: err.message, stack: err.stack }, 'UI crashed');
  process.exit(1);
}
