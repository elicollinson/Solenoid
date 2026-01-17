/**
 * Generic Executor Agent
 *
 * General-purpose text worker for knowledge-based tasks that don't require
 * specialized tools. Handles content creation, summarization, analysis,
 * and general knowledge questions. Has no external tool access.
 *
 * Capabilities:
 * - Answer general knowledge questions
 * - Write creative content (emails, documents, stories)
 * - Summarize and analyze provided text
 * - Generate structured content (lists, outlines, comparisons)
 */
import { BaseAgent } from './base-agent.js';
import type { Agent } from './types.js';
import { getAgentPrompt, getModelConfig, loadSettings } from '../config/index.js';

const DEFAULT_INSTRUCTION = `You are the Generic Executor Agent, handling knowledge tasks.

### ROLE
You handle general-purpose tasks. You are the "knowledge worker" for text-based work.

### CAPABILITIES

**You CAN do:**
- Answer general knowledge questions
- Write creative content (poems, stories, emails, etc.)
- Summarize or analyze provided text
- Generate structured content (lists, outlines, comparisons)
- Draft documents, messages, or responses

**You CANNOT do:**
- Execute Python code (use code_executor_agent)
- Generate charts or visualizations (use chart_generator_agent)
- Search the web for current information (use research_agent)
- Access files or external systems (use mcp_agent)

### CONSTRAINTS
- ALWAYS provide helpful, accurate responses
- ALWAYS transfer your result to your parent agent upon completion
- If asked to do something outside your capabilities, clearly state what agent should be used instead`;

export function createGenericAgent(): Agent {
  let settings;
  try {
    settings = loadSettings();
  } catch {
    settings = null;
  }

  const modelConfig = settings
    ? getModelConfig('generic_executor_agent', settings)
    : { name: 'llama3.1:8b', provider: 'ollama_chat' as const, context_length: 128000 };

  const customPrompt = settings
    ? getAgentPrompt('generic_executor_agent', settings)
    : undefined;

  return new BaseAgent({
    name: 'generic_executor_agent',
    model: modelConfig.name,
    instruction: customPrompt ?? DEFAULT_INSTRUCTION,
    disallowTransferToParent: true,
  });
}
