import { describe, it, expect, vi } from 'vitest';
import { BaseAgent } from '../../src/agents/base-agent.js';
import type { ToolDefinition } from '../../src/llm/types.js';

// Mock the Ollama provider
vi.mock('../../src/llm/ollama.js', () => ({
  getOllamaProvider: vi.fn().mockReturnValue({
    chat: vi.fn(),
    chatStream: vi.fn(),
  }),
}));

describe('BaseAgent', () => {
  describe('constructor', () => {
    it('should create agent with required properties', () => {
      const agent = new BaseAgent({
        name: 'test_agent',
        model: 'llama3.1:8b',
        instruction: 'You are a test agent.',
      });

      expect(agent.name).toBe('test_agent');
      expect(agent.config.model).toBe('llama3.1:8b');
      expect(agent.config.instruction).toBe('You are a test agent.');
    });

    it('should initialize with config containing tools and subAgents', () => {
      const agent = new BaseAgent({
        name: 'test_agent',
        model: 'llama3.1:8b',
        instruction: 'Test',
      });

      expect(agent.config.tools).toBeUndefined();
      expect(agent.config.subAgents).toBeUndefined();
    });
  });

  describe('config', () => {
    it('should store provided tools in config', () => {
      const testTool: ToolDefinition = {
        type: 'function',
        function: {
          name: 'test_tool',
          description: 'A test tool',
          parameters: {
            type: 'object',
            properties: {
              input: { type: 'string', description: 'Input string' },
            },
            required: ['input'],
          },
        },
      };

      const agent = new BaseAgent({
        name: 'test_agent',
        model: 'llama3.1:8b',
        instruction: 'Test',
        tools: [testTool],
      });

      expect(agent.config.tools?.length).toBe(1);
      expect(agent.config.tools?.[0].function.name).toBe('test_tool');
    });
  });

  describe('sub-agents', () => {
    it('should store sub-agents in config', () => {
      const subAgent = new BaseAgent({
        name: 'sub_agent',
        model: 'llama3.1:8b',
        instruction: 'Sub agent',
      });

      const agent = new BaseAgent({
        name: 'parent_agent',
        model: 'llama3.1:8b',
        instruction: 'Parent agent',
        subAgents: [subAgent],
      });

      expect(agent.config.subAgents?.length).toBe(1);
      expect(agent.config.subAgents?.[0].name).toBe('sub_agent');
    });
  });

  describe('callbacks', () => {
    it('should store beforeModelCallback in config', async () => {
      const beforeCallback = vi.fn().mockResolvedValue(undefined);

      const agent = new BaseAgent({
        name: 'test_agent',
        model: 'llama3.1:8b',
        instruction: 'Test',
        beforeModelCallback: beforeCallback,
      });

      expect(agent.config.beforeModelCallback).toBe(beforeCallback);
    });

    it('should store afterModelCallback in config', async () => {
      const afterCallback = vi.fn().mockResolvedValue(undefined);

      const agent = new BaseAgent({
        name: 'test_agent',
        model: 'llama3.1:8b',
        instruction: 'Test',
        afterModelCallback: afterCallback,
      });

      expect(agent.config.afterModelCallback).toBe(afterCallback);
    });
  });
});
