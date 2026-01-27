/**
 * Generic Executor Agent (ADK)
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
 *
 * Dependencies:
 * - @google/adk: LlmAgent for ADK-compatible agent
 */
import { LlmAgent } from '@google/adk';
import type { AppSettings } from '../config/index.js';
import { getAdkModelName, getAgentPrompt, loadSettings } from '../config/index.js';
import { saveMemoriesOnFinalResponse } from '../memory/callbacks.js';

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

// Load settings with fallback
let settings: AppSettings | null;
try {
  settings = loadSettings();
} catch {
  settings = null;
}

const modelName = settings
  ? getAdkModelName('generic_executor_agent', settings)
  : 'gemini-2.5-flash';

const customPrompt = settings ? getAgentPrompt('generic_executor_agent', settings) : undefined;

/**
 * Generic Executor LlmAgent - handles knowledge-based text tasks
 */
export const genericAgent = new LlmAgent({
  name: 'generic_executor_agent',
  model: modelName,
  description:
    'General-purpose knowledge worker for text-based tasks like writing, summarization, and analysis.',
  instruction: customPrompt ?? DEFAULT_INSTRUCTION,
  afterModelCallback: saveMemoriesOnFinalResponse,
});

// Factory function for backwards compatibility
export function createGenericAgent(): LlmAgent {
  return genericAgent;
}
