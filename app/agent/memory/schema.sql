-- Core tables for long-term memories and optional knowledge base chunks.
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

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
USING fts5(text, content='memories', content_rowid='id');

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

CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec
USING vec0(embedding float[256], mem_id int);

CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_mem_app  ON memories(app_name);
CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(memory_type);

CREATE TABLE IF NOT EXISTS kb_chunks(
  id          INTEGER PRIMARY KEY,
  doc_id      TEXT,
  title       TEXT,
  text        TEXT NOT NULL,
  meta_json   TEXT DEFAULT '{}',
  created_at  INTEGER NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(text, content='kb_chunks', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS kb_ai AFTER INSERT ON kb_chunks BEGIN
  INSERT INTO kb_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS kb_ad AFTER DELETE ON kb_chunks BEGIN
  INSERT INTO kb_fts(kb_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS kb_au AFTER UPDATE ON kb_chunks BEGIN
  INSERT INTO kb_fts(kb_fts, rowid, text) VALUES('delete', old.id, old.text);
  INSERT INTO kb_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS kb_vec
USING vec0(embedding float[256], chunk_id int);
