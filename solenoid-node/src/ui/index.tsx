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
