/**
 * Hybrid Memory Search
 *
 * Implements hybrid retrieval combining dense vector search (semantic similarity)
 * and sparse BM25 search (keyword matching). Uses Reciprocal Rank Fusion (RRF)
 * to merge results from both retrieval methods for improved accuracy.
 *
 * Algorithm:
 * 1. Dense search via sqlite-vec for semantic similarity
 * 2. Sparse search via FTS5 for keyword matching
 * 3. RRF fusion to combine and re-rank results
 */
import type { Database } from 'bun:sqlite';
import type { EmbeddingsService } from './embeddings.js';
import type { MemoryRow, SearchResult } from './schema.js';

function rrf(rank: number): number {
  return 1.0 / (60.0 + rank);
}

function sanitizeQuery(query: string): string {
  return query
    .split('')
    .filter((c) => /[\w\s]/.test(c))
    .join('');
}

interface DenseResult {
  id: number;
  text: string;
  memory_type: string;
  source: string | null;
  importance: number;
  distance: number;
}

interface SparseResult {
  id: number;
  text: string;
  memory_type: string;
  source: string | null;
  importance: number;
  bm25_score: number;
}

export async function searchMemories(
  db: Database,
  query: string,
  userId: string,
  appName: string,
  embedder: EmbeddingsService,
  options: {
    topN?: number;
    denseLimit?: number;
    sparseLimit?: number;
    fuseTopK?: number;
  } = {}
): Promise<SearchResult[]> {
  const { topN = 12, denseLimit = 80, sparseLimit = 80, fuseTopK = 30 } = options;

  const safeQuery = sanitizeQuery(query);
  if (!safeQuery.trim()) {
    return [];
  }

  const candidates = await hybridCandidates(
    db,
    safeQuery,
    userId,
    appName,
    embedder,
    denseLimit,
    sparseLimit,
    fuseTopK
  );

  return candidates.slice(0, topN).map(({ memory, score }) => ({
    text: memory.text,
    score,
    memory,
  }));
}

async function hybridCandidates(
  db: Database,
  query: string,
  userId: string,
  appName: string,
  embedder: EmbeddingsService,
  denseLimit: number,
  sparseLimit: number,
  fuseTopK: number
): Promise<Array<{ memory: MemoryRow; score: number }>> {
  const scores: Map<number, number> = new Map();
  const candidates: Map<number, MemoryRow> = new Map();

  let denseRows: DenseResult[] = [];
  try {
    const queryVec = await embedder.embedQuery(query);
    const queryBlob = embedder.toBlob(queryVec);

    // sqlite-vec uses MATCH for KNN search with the query vector
    const stmt = db.prepare(`
      SELECT m.id, m.text, m.memory_type, m.source, m.importance, v.distance
      FROM memories_vec AS v
      JOIN memories AS m ON m.id = v.mem_id
      WHERE m.user_id = ? AND m.app_name = ? AND v.embedding MATCH ? AND k = ?
      ORDER BY v.distance
      LIMIT ?
    `);

    denseRows = stmt.all(userId, appName, queryBlob, denseLimit, denseLimit) as DenseResult[];
  } catch {
    // Vector search not available
  }

  for (let rank = 0; rank < denseRows.length; rank++) {
    const row = denseRows[rank]!;
    const memory = rowToMemory(row);
    candidates.set(memory.id, memory);
    scores.set(memory.id, (scores.get(memory.id) ?? 0) + rrf(rank + 1));
  }

  let sparseRows: SparseResult[] = [];
  try {
    const stmt = db.prepare(`
      SELECT m.id, m.text, m.memory_type, m.source, m.importance, bm25(memories_fts) AS bm25_score
      FROM memories_fts
      JOIN memories AS m ON memories_fts.rowid = m.id
      WHERE m.user_id = ? AND m.app_name = ? AND memories_fts MATCH ?
      ORDER BY bm25_score
      LIMIT ?
    `);

    sparseRows = stmt.all(userId, appName, query, sparseLimit) as SparseResult[];
  } catch {
    // FTS search not available
  }

  for (let rank = 0; rank < sparseRows.length; rank++) {
    const row = sparseRows[rank]!;
    const memory = rowToMemory(row);
    candidates.set(memory.id, memory);
    scores.set(memory.id, (scores.get(memory.id) ?? 0) + rrf(rank + 1));
  }

  const fused = Array.from(scores.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, fuseTopK);

  return fused.map(([id, score]) => ({
    memory: candidates.get(id)!,
    score,
  }));
}

function rowToMemory(row: DenseResult | SparseResult): MemoryRow {
  return {
    id: row.id,
    user_id: '',
    app_name: '',
    memory_type: row.memory_type as MemoryRow['memory_type'],
    text: row.text,
    source: row.source,
    importance: row.importance,
    tags_json: '[]',
    created_at: 0,
    expires_at: null,
  };
}
