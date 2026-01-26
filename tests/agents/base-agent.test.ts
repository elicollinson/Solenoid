import { describe, it, expect } from 'vitest';
import { LlmAgent } from '@google/adk';

describe('LlmAgent (ADK)', () => {
  describe('constructor', () => {
    it('should create agent with required properties', () => {
      const agent = new LlmAgent({
        name: 'test_agent',
        model: 'gemini-2.5-flash',
        instruction: 'You are a test agent.',
      });

      expect(agent.name).toBe('test_agent');
      expect(agent.model).toBe('gemini-2.5-flash');
      expect(agent.instruction).toBe('You are a test agent.');
    });

    it('should initialize with empty tools array by default', () => {
      const agent = new LlmAgent({
        name: 'test_agent',
        model: 'gemini-2.5-flash',
        instruction: 'Test',
      });

      expect(agent.tools).toHaveLength(0);
    });
  });

  describe('sub-agents', () => {
    it('should store sub-agents', () => {
      const subAgent = new LlmAgent({
        name: 'sub_agent',
        model: 'gemini-2.5-flash',
        instruction: 'Sub agent',
      });

      const agent = new LlmAgent({
        name: 'parent_agent',
        model: 'gemini-2.5-flash',
        instruction: 'Parent agent',
        subAgents: [subAgent],
      });

      expect(agent.subAgents?.length).toBe(1);
      expect(agent.subAgents?.[0].name).toBe('sub_agent');
    });
  });

  describe('callbacks', () => {
    it('should store beforeModelCallback', () => {
      const beforeCallback = async () => undefined;

      const agent = new LlmAgent({
        name: 'test_agent',
        model: 'gemini-2.5-flash',
        instruction: 'Test',
        beforeModelCallback: beforeCallback,
      });

      expect(agent.beforeModelCallback).toBe(beforeCallback);
    });

    it('should store afterModelCallback', () => {
      const afterCallback = async () => undefined;

      const agent = new LlmAgent({
        name: 'test_agent',
        model: 'gemini-2.5-flash',
        instruction: 'Test',
        afterModelCallback: afterCallback,
      });

      expect(agent.afterModelCallback).toBe(afterCallback);
    });
  });

  describe('disallowTransferToParent', () => {
    it('should default to false', () => {
      const agent = new LlmAgent({
        name: 'test_agent',
        model: 'gemini-2.5-flash',
        instruction: 'Test',
      });

      expect(agent.disallowTransferToParent).toBe(false);
    });

    it('should allow setting to true', () => {
      const agent = new LlmAgent({
        name: 'test_agent',
        model: 'gemini-2.5-flash',
        instruction: 'Test',
        disallowTransferToParent: true,
      });

      expect(agent.disallowTransferToParent).toBe(true);
    });
  });
});
