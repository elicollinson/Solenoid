import { describe, it, expect, mock } from 'bun:test';

// Mock the embeddings service
mock.module('../../src/memory/embeddings.js', () => ({
  EmbeddingsService: class MockEmbeddingsService {
    private model: string;
    private host: string;

    constructor(host: string, model: string) {
      this.host = host;
      this.model = model;
    }

    async embedQuery(text: string): Promise<Float32Array> {
      const embedding = new Array(256).fill(0);
      for (let i = 0; i < text.length && i < 256; i++) {
        embedding[i] = text.charCodeAt(i) / 256;
      }
      return new Float32Array(embedding);
    }

    async embedDocument(text: string): Promise<Float32Array> {
      return this.embedQuery(text);
    }

    toBlob(vec: Float32Array): Buffer {
      return Buffer.from(vec.buffer);
    }
  },
  getEmbeddingsService: () => ({
    async embedQuery(text: string): Promise<Float32Array> {
      const embedding = new Array(256).fill(0);
      for (let i = 0; i < text.length && i < 256; i++) {
        embedding[i] = text.charCodeAt(i) / 256;
      }
      return new Float32Array(embedding);
    },
    async embedDocument(text: string): Promise<Float32Array> {
      const embedding = new Array(256).fill(0);
      for (let i = 0; i < text.length && i < 256; i++) {
        embedding[i] = text.charCodeAt(i) / 256;
      }
      return new Float32Array(embedding);
    },
    toBlob(vec: Float32Array): Buffer {
      return Buffer.from(vec.buffer);
    },
  }),
}));

describe('EmbeddingsService (mocked)', () => {
  it('should create embeddings service', async () => {
    const { getEmbeddingsService } = await import('../../src/memory/embeddings.js');
    const service = getEmbeddingsService('http://localhost:11434', 'nomic-embed-text');

    expect(service).toBeDefined();
    expect(typeof service.embedQuery).toBe('function');
  });

  it('should generate embeddings', async () => {
    const { getEmbeddingsService } = await import('../../src/memory/embeddings.js');
    const service = getEmbeddingsService('http://localhost:11434', 'nomic-embed-text');

    const embedding = await service.embedQuery('test text');
    expect(embedding).toBeInstanceOf(Float32Array);
    expect(embedding.length).toBe(256);
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
