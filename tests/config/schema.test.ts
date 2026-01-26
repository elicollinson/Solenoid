import { describe, it, expect } from 'bun:test';
import { AppSettingsSchema, ModelConfigSchema, EmbeddingsConfigSchema } from '../../src/config/schema.js';

describe('Config Schema', () => {
  describe('ModelConfigSchema', () => {
    it('should validate a complete model config', () => {
      const config = {
        provider: 'ollama_chat',
        name: 'llama3.1:8b',
        context_length: 128000,
      };

      const result = ModelConfigSchema.safeParse(config);
      expect(result.success).toBe(true);
    });

    it('should apply defaults for missing optional fields', () => {
      const config = {
        provider: 'ollama_chat',
        name: 'llama3.1:8b',
      };

      const result = ModelConfigSchema.safeParse(config);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.context_length).toBe(128000);
      }
    });

    it('should reject invalid provider', () => {
      const config = {
        provider: 'invalid_provider',
        name: 'llama3.1:8b',
      };

      const result = ModelConfigSchema.safeParse(config);
      expect(result.success).toBe(false);
    });
  });

  describe('EmbeddingsConfigSchema', () => {
    it('should validate embeddings config', () => {
      const config = {
        provider: 'ollama',
        model: 'nomic-embed-text',
        host: 'http://localhost:11434',
      };

      const result = EmbeddingsConfigSchema.safeParse(config);
      expect(result.success).toBe(true);
    });

    it('should apply default host', () => {
      const config = {
        provider: 'ollama',
        model: 'nomic-embed-text',
      };

      const result = EmbeddingsConfigSchema.safeParse(config);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.host).toBe('http://localhost:11434');
      }
    });
  });

  describe('AppSettingsSchema', () => {
    it('should validate complete app settings', () => {
      const settings = {
        models: {
          default: {
            provider: 'ollama_chat',
            name: 'llama3.1:8b',
            context_length: 128000,
          },
          agents: {},
        },
        embeddings: {
          provider: 'ollama',
          model: 'nomic-embed-text',
        },
        prompts: {},
        mcp_servers: {},
      };

      const result = AppSettingsSchema.safeParse(settings);
      expect(result.success).toBe(true);
    });

    it('should validate settings with MCP servers', () => {
      const settings = {
        models: {
          default: {
            provider: 'ollama_chat',
            name: 'llama3.1:8b',
          },
        },
        embeddings: {
          provider: 'ollama',
          model: 'nomic-embed-text',
        },
        mcp_servers: {
          filesystem: {
            type: 'stdio',
            command: 'npx',
            args: ['@modelcontextprotocol/server-filesystem'],
          },
          context7: {
            type: 'http',
            url: 'https://mcp.context7.com/api/v1',
            headers: { Authorization: 'Bearer token' },
          },
        },
      };

      const result = AppSettingsSchema.safeParse(settings);
      expect(result.success).toBe(true);
    });
  });
});
