/**
 * Memory Database
 *
 * SQLite database initialization with WAL mode for performance. Loads the
 * memory schema and optionally the sqlite-vec extension for vector search.
 * Falls back gracefully if vector extension is unavailable.
 *
 * Dependencies:
 * - better-sqlite3: Synchronous SQLite3 binding for Node.js with native performance
 */
import Database from 'better-sqlite3';
import { MEMORY_SCHEMA } from './schema.js';

export function createDatabase(dbPath: string): Database.Database {
  const db = new Database(dbPath);

  db.pragma('journal_mode = WAL');
  db.pragma('synchronous = NORMAL');

  try {
    db.loadExtension('vec0');
  } catch {
    console.warn(
      'sqlite-vec extension not found. Vector search will be disabled.'
    );
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
        console.warn(`Schema warning: ${error.message}`);
      }
    }
  }

  return db;
}

export function closeDatabase(db: Database.Database): void {
  db.close();
}
