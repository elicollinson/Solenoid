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

let instance: ReturnType<typeof render> | null = null;

// Handle SIGINT/SIGTERM for clean shutdown (prevents tsx watch restart)
const handleSignal = (signal: string) => {
  uiLogger.info({ signal }, 'Received signal, shutting down');
  if (instance) {
    instance.unmount();
  }
  process.exit(0);
};

process.on('SIGINT', () => handleSignal('SIGINT'));
process.on('SIGTERM', () => handleSignal('SIGTERM'));

try {
  // Disable Ink's default Ctrl+C handling - we handle it in App component
  instance = render(<App />, { exitOnCtrlC: false });
  uiLogger.info('UI rendered successfully');
  await instance.waitUntilExit();
  uiLogger.info('UI exited normally');
  process.exit(0);
} catch (error) {
  const err = error instanceof Error ? error : new Error(String(error));
  uiLogger.fatal({ error: err.message, stack: err.stack }, 'UI crashed');
  process.exit(1);
}
