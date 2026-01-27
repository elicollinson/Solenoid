/**
 * Memory Database
 *
 * SQLite database initialization with WAL mode for performance. Uses Bun's
 * native SQLite implementation. Loads the memory schema and optionally the
 * sqlite-vec extension for vector search. Falls back gracefully if vector
 * extension is unavailable.
 *
 * Dependencies:
 * - bun:sqlite: Bun's native SQLite implementation with excellent performance
 */
import { Database } from 'bun:sqlite';
import { serverLogger } from '../utils/logger.js';
import { MEMORY_SCHEMA } from './schema.js';

export type BunDatabase = Database;

export function createDatabase(dbPath: string): Database {
  const db = new Database(dbPath, { create: true });

  db.exec('PRAGMA journal_mode = WAL');
  db.exec('PRAGMA synchronous = NORMAL');

  // Try to load sqlite-vec extension for vector search
  try {
    // sqlite-vec extension paths vary by platform
    // Common locations: vec0, sqlite-vec, or full path
    db.loadExtension('vec0');
  } catch {
    try {
      // Try alternative extension name
      db.loadExtension('sqlite-vec');
    } catch {
      serverLogger.warn('sqlite-vec extension not found. Vector search will be disabled.');
    }
  }

  const statements = MEMORY_SCHEMA.split(';')
    .map((s) => s.trim())
    .filter((s) => s.length > 0);

  for (const statement of statements) {
    try {
      db.exec(statement);
    } catch (error) {
      if (
        error instanceof Error &&
        !error.message.includes('already exists') &&
        !error.message.includes('no such module: vec0')
      ) {
        serverLogger.warn(`Schema warning: ${error.message}`);
      }
    }
  }

  return db;
}

export function closeDatabase(db: Database): void {
  db.close();
}
