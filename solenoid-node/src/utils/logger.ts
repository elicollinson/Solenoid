import pino from 'pino';
import { existsSync, mkdirSync } from 'fs';
import { join } from 'path';

const LOG_DIR = join(process.cwd(), 'logs');

// Ensure log directory exists
if (!existsSync(LOG_DIR)) {
  mkdirSync(LOG_DIR, { recursive: true });
}

function createLogger(name: string) {
  const logFile = join(LOG_DIR, `${name}.log`);

  return pino(
    {
      name,
      level: process.env['LOG_LEVEL'] ?? 'debug',
      timestamp: pino.stdTimeFunctions.isoTime,
    },
    pino.destination({
      dest: logFile,
      sync: false,
    })
  );
}

// Separate loggers for different parts of the app
export const serverLogger = createLogger('server');
export const uiLogger = createLogger('ui');
export const agentLogger = createLogger('agent');

// Helper to log uncaught errors
export function setupErrorHandlers(logger: pino.Logger) {
  process.on('uncaughtException', (error) => {
    logger.fatal({ error: error.message, stack: error.stack }, 'Uncaught exception');
    // Give time for log to flush
    setTimeout(() => process.exit(1), 100);
  });

  process.on('unhandledRejection', (reason) => {
    const error = reason instanceof Error ? reason : new Error(String(reason));
    logger.error({ error: error.message, stack: error.stack }, 'Unhandled rejection');
  });
}
