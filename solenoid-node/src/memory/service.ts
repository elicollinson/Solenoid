/**
 * Memory Service
 *
 * High-level API for memory storage and retrieval. Coordinates database
 * operations, embedding generation, and hybrid search. Manages the lifecycle
 * of memory entries including creation, search, and deletion.
 *
 * Memory types:
 * - profile: User preferences and persistent facts
 * - episodic: Conversation history and interactions
 * - semantic: Extracted knowledge and learned concepts
 */
import type Database from 'better-sqlite3';
import { createDatabase, closeDatabase } from './database.js';
import { EmbeddingsService, getEmbeddingsService } from './embeddings.js';
import { searchMemories } from './search.js';
import type { MemoryInput, MemoryRow, MemoryType, SearchResult } from './schema.js';

export interface MemoryServiceOptions {
  dbPath: string;
  ollamaHost?: string;
  embeddingModel?: string;
  denseLimit?: number;
  sparseLimit?: number;
  fuseTopK?: number;
  topN?: number;
}

export class MemoryService {
  private db: Database.Database;
  private embedder: EmbeddingsService;
  private options: Required<Omit<MemoryServiceOptions, 'dbPath'>>;

  constructor(options: MemoryServiceOptions) {
    this.db = createDatabase(options.dbPath);
    this.embedder = getEmbeddingsService(options.ollamaHost, options.embeddingModel);
    this.options = {
      ollamaHost: options.ollamaHost ?? 'http://localhost:11434',
      embeddingModel: options.embeddingModel ?? 'nomic-embed-text',
      denseLimit: options.denseLimit ?? 80,
      sparseLimit: options.sparseLimit ?? 80,
      fuseTopK: options.fuseTopK ?? 30,
      topN: options.topN ?? 12,
    };
  }

  async addMemory(input: MemoryInput): Promise<number> {
    const now = Math.floor(Date.now() / 1000);
    const tagsJson = JSON.stringify(input.tags ?? []);

    const stmt = this.db.prepare(`
      INSERT INTO memories(user_id, app_name, memory_type, text, source,
                          importance, tags_json, created_at, expires_at)
      VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    const result = stmt.run(
      input.user_id,
      input.app_name,
      input.memory_type,
      input.text,
      input.source ?? null,
      input.importance ?? 1,
      tagsJson,
      now,
      input.expires_at ?? null
    );

    const memId = Number(result.lastInsertRowid);

    try {
      const embedding = await this.embedder.embedDocument(input.text);
      const blob = this.embedder.toBlob(embedding);

      const vecStmt = this.db.prepare(`
        INSERT INTO memories_vec(rowid, embedding, mem_id)
        VALUES(?, ?, ?)
      `);
      vecStmt.run(memId, blob, memId);
    } catch (error) {
      console.warn('Failed to store embedding:', error);
    }

    return memId;
  }

  async search(
    query: string,
    userId: string,
    appName: string
  ): Promise<SearchResult[]> {
    return searchMemories(this.db, query, userId, appName, this.embedder, {
      topN: this.options.topN,
      denseLimit: this.options.denseLimit,
      sparseLimit: this.options.sparseLimit,
      fuseTopK: this.options.fuseTopK,
    });
  }

  getMemory(id: number): MemoryRow | null {
    const stmt = this.db.prepare('SELECT * FROM memories WHERE id = ?');
    return stmt.get(id) as MemoryRow | null;
  }

  getMemoriesByUser(
    userId: string,
    appName: string,
    memoryType?: MemoryType
  ): MemoryRow[] {
    let sql = 'SELECT * FROM memories WHERE user_id = ? AND app_name = ?';
    const params: Array<string | MemoryType> = [userId, appName];

    if (memoryType) {
      sql += ' AND memory_type = ?';
      params.push(memoryType);
    }

    sql += ' ORDER BY created_at DESC';

    const stmt = this.db.prepare(sql);
    return stmt.all(...params) as MemoryRow[];
  }

  deleteMemory(id: number): boolean {
    const stmt = this.db.prepare('DELETE FROM memories WHERE id = ?');
    const result = stmt.run(id);
    return result.changes > 0;
  }

  close(): void {
    closeDatabase(this.db);
  }
}

let defaultService: MemoryService | null = null;

export function getMemoryService(options?: MemoryServiceOptions): MemoryService {
  if (!defaultService) {
    if (!options) {
      throw new Error('MemoryService not initialized. Provide options on first call.');
    }
    defaultService = new MemoryService(options);
  }
  return defaultService;
}

export function closeMemoryService(): void {
  if (defaultService) {
    defaultService.close();
    defaultService = null;
  }
}
