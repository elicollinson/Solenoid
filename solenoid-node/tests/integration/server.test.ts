import { describe, it, expect, vi } from 'vitest';
import { createServer } from '../../src/server/index.js';

// Mock the agent factory to avoid LLM calls in tests
vi.mock('../../src/agents/index.js', () => ({
  createAgentHierarchy: vi.fn().mockResolvedValue({
    runner: {
      async *run(message: string) {
        yield { type: 'text', content: `Echo: ${message}` };
      },
    },
  }),
  createAgentHierarchySync: vi.fn().mockReturnValue({
    runner: {
      async *run(message: string) {
        yield { type: 'text', content: `Echo: ${message}` };
      },
    },
  }),
}));

// Mock config
vi.mock('../../src/config/index.js', () => ({
  loadSettings: vi.fn().mockReturnValue({
    models: {
      default: { provider: 'ollama_chat', name: 'llama3.1:8b', context_length: 128000 },
      agents: {},
    },
    embeddings: { provider: 'ollama', model: 'nomic-embed-text', host: 'http://localhost:11434' },
    prompts: {},
    mcp_servers: {},
  }),
}));

describe('Server', () => {
  const app = createServer();

  describe('GET /health', () => {
    it('should return health status', async () => {
      const response = await app.request('/health');
      expect(response.status).toBe(200);

      const data = await response.json();
      expect(data.status).toBe('healthy');
      expect(data.version).toBeDefined();
      expect(data.timestamp).toBeDefined();
    });
  });

  describe('GET /config', () => {
    it('should return configuration summary', async () => {
      const response = await app.request('/config');
      expect(response.status).toBe(200);

      const data = await response.json();
      expect(data.models).toBeDefined();
      expect(data.embeddings).toBeDefined();
    });
  });

  describe('POST /api/agent', () => {
    it('should reject requests without messages', async () => {
      const response = await app.request('/api/agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [] }),
      });

      // Should return 400 or similar for no user message
      const text = await response.text();
      expect(response.status).toBe(400);
    });

    it('should accept valid message format', async () => {
      const response = await app.request('/api/agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [{ role: 'user', content: 'Hello' }],
        }),
      });

      expect(response.status).toBe(200);
      expect(response.headers.get('content-type')).toContain('text/event-stream');
    });
  });
});
