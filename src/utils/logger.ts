/**
 * Logging Utilities
 *
 * Structured logging with file-based output. Creates separate log files for
 * server, UI, and agent components in the ./logs directory.
 * Includes global error handlers for uncaught exceptions and rejections.
 *
 * Uses Bun's native file I/O for performance.
 */
import { existsSync, mkdirSync, appendFileSync } from 'node:fs';
import { join } from 'node:path';

const LOG_DIR = join(process.cwd(), 'logs');

// Ensure log directory exists
if (!existsSync(LOG_DIR)) {
  mkdirSync(LOG_DIR, { recursive: true });
}

type LogLevel = 'trace' | 'debug' | 'info' | 'warn' | 'error' | 'fatal';

interface LogEntry {
  level: LogLevel;
  name: string;
  msg: string;
  time: string;
  [key: string]: unknown;
}

interface Logger {
  trace: (obj: object | string, msg?: string) => void;
  debug: (obj: object | string, msg?: string) => void;
  info: (obj: object | string, msg?: string) => void;
  warn: (obj: object | string, msg?: string) => void;
  error: (obj: object | string, msg?: string) => void;
  fatal: (obj: object | string, msg?: string) => void;
}

function createLogger(name: string): Logger {
  const logFile = join(LOG_DIR, `${name}.log`);
  const logLevel = (process.env['LOG_LEVEL'] ?? 'debug') as LogLevel;

  const levels: Record<LogLevel, number> = {
    trace: 5,
    debug: 10,
    info: 20,
    warn: 30,
    error: 40,
    fatal: 50,
  };

  const shouldLog = (level: LogLevel): boolean => {
    return levels[level] >= levels[logLevel];
  };

  const log = (level: LogLevel, obj: object | string, msg?: string): void => {
    if (!shouldLog(level)) return;

    const entry: LogEntry = {
      level,
      name,
      msg: typeof obj === 'string' ? obj : msg ?? '',
      time: new Date().toISOString(),
      ...(typeof obj === 'object' ? obj : {}),
    };

    const line = JSON.stringify(entry) + '\n';

    // Write to file asynchronously
    try {
      appendFileSync(logFile, line);
    } catch {
      // Ignore file write errors
    }
  };

  return {
    trace: (obj, msg) => log('trace', obj, msg),
    debug: (obj, msg) => log('debug', obj, msg),
    info: (obj, msg) => log('info', obj, msg),
    warn: (obj, msg) => log('warn', obj, msg),
    error: (obj, msg) => log('error', obj, msg),
    fatal: (obj, msg) => log('fatal', obj, msg),
  };
}

// Separate loggers for different parts of the app
export const serverLogger = createLogger('server');
export const uiLogger = createLogger('ui');
export const agentLogger = createLogger('agent');

// Helper to log uncaught errors
export function setupErrorHandlers(logger: Logger) {
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
