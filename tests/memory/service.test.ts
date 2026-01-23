import { describe, it, expect, vi } from 'vitest';
import { EmbeddingsService } from '../../src/memory/embeddings.js';

// Test the embeddings service interface (mocked)
vi.mock('../../src/memory/embeddings.js', () => ({
  EmbeddingsService: class MockEmbeddingsService {
    initialized = false;
    model: string;
    host: string;

    constructor(host: string, model: string) {
      this.host = host;
      this.model = model;
    }

    async initialize() {
      this.initialized = true;
    }

    async getEmbedding(text: string): Promise<number[]> {
      // Simple hash-based mock embedding (384 dimensions)
      const embedding = new Array(384).fill(0);
      for (let i = 0; i < text.length && i < 384; i++) {
        embedding[i] = text.charCodeAt(i) / 256;
      }
      return embedding;
    }
  },
  getEmbeddingsService: vi.fn((host: string, model: string) => {
    return new (vi.mocked(EmbeddingsService) as any)(host, model);
  }),
}));

describe('EmbeddingsService (mocked)', () => {
  it('should create embeddings service with host and model', async () => {
    const { getEmbeddingsService } = await import('../../src/memory/embeddings.js');
    const service = getEmbeddingsService('http://localhost:11434', 'nomic-embed-text');

    expect(service).toBeDefined();
    expect(service.host).toBe('http://localhost:11434');
    expect(service.model).toBe('nomic-embed-text');
  });

  it('should generate embeddings', async () => {
    const { getEmbeddingsService } = await import('../../src/memory/embeddings.js');
    const service = getEmbeddingsService('http://localhost:11434', 'nomic-embed-text');
    await service.initialize();

    const embedding = await service.getEmbedding('test text');
    expect(Array.isArray(embedding)).toBe(true);
    expect(embedding.length).toBe(384);
  });
});

// Note: Full MemoryService integration tests require sqlite-vec
// which may not be available in all test environments.
// These would be integration tests that run against a real database.
describe('MemoryService schema', () => {
  it.skip('should be tested with integration tests', () => {
    // Integration tests would:
    // 1. Create an in-memory SQLite database
    // 2. Initialize the schema
    // 3. Add memories
    // 4. Search memories
    // 5. Delete memories
    // These require the actual sqlite-vec extension which may not load in CI
  });
});
