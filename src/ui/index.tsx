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
import { setLogLevel, LogLevel } from '@google/adk';
import { App } from './app.js';
import { uiLogger, setupErrorHandlers } from '../utils/logger.js';

// Suppress ADK console logs - set to higher than ERROR (3) to suppress all
// Must be called before any ADK code runs
setLogLevel((LogLevel.ERROR + 1) as unknown as LogLevel);

// Set up error handlers to catch crashes
setupErrorHandlers(uiLogger);

uiLogger.info('Starting Solenoid UI');

try {
  const instance = render(<App />);
  uiLogger.info('UI rendered successfully');
  await instance.waitUntilExit();
  uiLogger.info('UI exited normally');
  // Force exit - MCP connections and other async operations may keep process alive
  process.exit(0);
} catch (error) {
  const err = error instanceof Error ? error : new Error(String(error));
  uiLogger.fatal({ error: err.message, stack: err.stack }, 'UI crashed');
  process.exit(1);
}
