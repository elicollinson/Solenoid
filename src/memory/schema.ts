/**
 * Memory Database Schema
 *
 * SQLite schema and TypeScript interfaces for the memory system. Defines
 * three memory types (profile, episodic, semantic) with support for both
 * keyword search (FTS5) and vector similarity search (sqlite-vec).
 *
 * Tables:
 * - memories: Main storage for memory entries with metadata
 * - memories_fts: FTS5 virtual table for BM25 keyword search
 * - memories_vec: sqlite-vec virtual table for dense vector search
 */
export const MEMORY_SCHEMA = `
-- Main memories table
CREATE TABLE IF NOT EXISTS memories (
  id            INTEGER PRIMARY KEY,
  user_id       TEXT NOT NULL,
  app_name      TEXT NOT NULL,
  memory_type   TEXT NOT NULL CHECK (memory_type IN ('profile','episodic','semantic')),
  text          TEXT NOT NULL,
  source        TEXT,
  importance    INTEGER DEFAULT 1,
  tags_json     TEXT DEFAULT '[]',
  created_at    INTEGER NOT NULL,
  expires_at    INTEGER
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_mem_app  ON memories(app_name);
CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(memory_type);

-- FTS5 virtual table for keyword/semantic search
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
USING fts5(text, content='memories', content_rowid='id');

-- Auto-sync triggers for FTS5
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, text) VALUES('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, text) VALUES('delete', old.id, old.text);
  INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;

-- sqlite-vec virtual table for dense vector search
CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec
USING vec0(embedding float[256], mem_id int);
`;

export type MemoryType = 'profile' | 'episodic' | 'semantic';

export interface MemoryRow {
  id: number;
  user_id: string;
  app_name: string;
  memory_type: MemoryType;
  text: string;
  source: string | null;
  importance: number;
  tags_json: string;
  created_at: number;
  expires_at: number | null;
}

export interface MemoryInput {
  user_id: string;
  app_name: string;
  memory_type: MemoryType;
  text: string;
  source?: string;
  importance?: number;
  tags?: string[];
  expires_at?: number;
}

export interface SearchResult {
  text: string;
  score: number;
  memory: MemoryRow;
}
