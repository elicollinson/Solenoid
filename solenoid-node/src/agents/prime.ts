/**
 * Prime Agent / Router (ADK)
 *
 * Intelligent router that decides whether to answer directly from knowledge
 * or delegate to the planning system. Simple factual questions are answered
 * immediately; tasks requiring tools, research, or multi-step execution are
 * forwarded to the planning_agent.
 *
 * Delegation triggers:
 * - Code execution, calculations, or algorithm generation
 * - Chart/visualization creation
 * - Current/live data from web searches
 * - Research requiring sources and citations
 * - File operations via MCP
 * - Multi-step composite tasks
 *
 * Dependencies:
 * - @google/adk: LlmAgent for ADK-compatible agent with subAgents
 */
import { LlmAgent } from '@google/adk';
import { getAgentPrompt, loadSettings, getAdkModelName } from '../config/index.js';
import { saveMemoriesOnFinalResponse } from '../memory/callbacks.js';
import { planningAgent, createPlanningAgent } from './planning.js';

const DEFAULT_INSTRUCTION = `You are the Prime Agent, the intelligent router of the agent system.

### ROLE
You determine whether a request can be answered directly or requires delegation to the planning system. Your goal is efficiency: handle simple tasks instantly, delegate complex ones appropriately.

### DECISION FRAMEWORK

**ANSWER DIRECTLY** (do NOT delegate) for:
- Factual questions: capitals, dates, definitions, "what is X?"
- Simple explanations: "explain X", "what does Y mean?"
- Yes/no questions with clear answers
- Lists from general knowledge: "name 3 types of..."
- Opinions or recommendations not requiring current data

**DELEGATE to planning_agent** when request involves ANY of:
- Code execution or calculations (factorial, algorithms, sequences)
- Generating number sequences (Fibonacci, primes, etc.)
- Chart/visualization generation
- Current/live data from the web (prices, news, recent events)
- Research with sources/citations required
- File operations (read/write files)
- Multi-step tasks combining multiple capabilities

### QUICK TEST
Ask yourself:
1. Does this need tools (code, charts, web search, files)?
2. Does this ask for sources, citations, or "research"?

If EITHER is YES → Delegate to planning_agent.
If BOTH are NO → Answer directly.

### WORKFLOW
1. **Quick Test**: Can I answer from knowledge? If yes, answer directly.
2. **If delegating**: Transfer to planning_agent with full context.
3. **Return**: Always transfer your result back to your parent agent when done.

### CONSTRAINTS
- NEVER delegate simple factual questions—answer them yourself.
- NEVER attempt tasks requiring tools yourself.
- ALWAYS transfer your final result to your parent agent upon completion.
- Keep direct answers concise but complete.`;

// Load settings with fallback
let settings;
try {
  settings = loadSettings();
} catch {
  settings = null;
}

const modelName = settings
  ? getAdkModelName('prime_agent', settings)
  : 'gemini-2.5-flash';

const customPrompt = settings ? getAgentPrompt('prime_agent', settings) : undefined;

/**
 * Prime LlmAgent - intelligent router that decides direct answer vs delegation
 */
export const primeAgent = new LlmAgent({
  name: 'prime_agent',
  model: modelName,
  description: 'Intelligent router that delegates to planning or answers directly.',
  instruction: customPrompt ?? DEFAULT_INSTRUCTION,
  afterModelCallback: saveMemoriesOnFinalResponse,
  subAgents: [planningAgent],
});

/**
 * Creates a prime agent with fully initialized MCP tools
 * Use this when you need MCP tools to be fully initialized
 */
export async function createPrimeAgent(): Promise<LlmAgent> {
  const initializedPlanningAgent = await createPlanningAgent();

  return new LlmAgent({
    name: 'prime_agent',
    model: modelName,
    description: 'Intelligent router that delegates to planning or answers directly.',
    instruction: customPrompt ?? DEFAULT_INSTRUCTION,
    afterModelCallback: saveMemoriesOnFinalResponse,
    subAgents: [initializedPlanningAgent],
  });
}
