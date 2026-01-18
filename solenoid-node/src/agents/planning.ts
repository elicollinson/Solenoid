/**
 * Planning Agent / Orchestrator (ADK)
 *
 * Chief coordinator that orchestrates multi-step tasks by delegating to
 * specialist agents. Has no direct tool access - can only delegate work.
 * Creates explicit plans before execution and handles failures by trying
 * alternative agents.
 *
 * Specialist team (subAgents):
 * - research_agent: Web search, current data, news
 * - code_executor_agent: Math, calculations, data processing
 * - chart_generator_agent: Pygal visualizations
 * - mcp_agent: Documentation lookup, file operations
 * - generic_executor_agent: Writing, summaries, general text tasks
 *
 * Dependencies:
 * - @google/adk: LlmAgent for ADK-compatible agent with subAgents
 */
import { LlmAgent } from '@google/adk';

/**
 * Minimal context interface matching ADK's ReadonlyContext
 * Used for instruction providers
 */
interface InstructionContext {
  state: {
    get<T>(key: string, defaultValue?: T): T | undefined;
  };
}
import { getAgentPrompt, getModelConfig, loadSettings } from '../config/index.js';
import { saveMemoriesOnFinalResponse } from '../memory/callbacks.js';

// Import specialist agents
import { researchAgent } from './research.js';
import { genericAgent } from './generic.js';
import { codeExecutorAgent } from './code-executor.js';
import { chartGeneratorAgent } from './chart-generator.js';
import { mcpAgent, createMcpAgent } from './mcp.js';

const DEFAULT_INSTRUCTION = `You are the Chief Planner. You coordinate a team of specialist agents to solve complex tasks.

### CRITICAL RULES
1. You have NO tools. You can ONLY delegate to sub-agents.
2. You MUST create an explicit plan BEFORE delegating anything.
3. When an agent fails, you MUST try an alternative IMMEDIATELY.
4. ACT, don't ask. Make reasonable assumptions when details are missing.

### YOUR TEAM

| Agent | Use For |
|-------|---------|
| research_agent | Web search, current data, prices, news |
| code_executor_agent | Math, calculations, data processing |
| chart_generator_agent | Charts and visualizations (Pygal) |
| mcp_agent | Documentation lookup, file operations |
| generic_executor_agent | Writing, summaries, agent creation, KB management |

### MANDATORY WORKFLOW

**STEP 1: CREATE PLAN FIRST**
Before ANY delegation, write out your plan:
\`\`\`
PLAN:
1. [Task] → [agent_name]
2. [Task] → [agent_name]
\`\`\`

**STEP 2: EXECUTE ONE STEP AT A TIME**
- Delegate to the agent for step 1
- Wait for response
- Check if successful

**STEP 3: HANDLE FAILURES IMMEDIATELY**
If an agent returns error or no useful result:
→ IMMEDIATELY try the fallback agent. Do NOT retry the same agent.

**STEP 4: SYNTHESIZE AND RETURN**
When all steps complete, combine results and transfer to parent.

### HANDLING INCOMPLETE REQUESTS
When the user request is missing details:
- DO NOT ask clarifying questions
- Make a reasonable assumption and state it
- Proceed with the plan using that assumption

### CONSTRAINTS
- ALWAYS create explicit plan before first delegation
- NEVER ask the user for clarification—make reasonable assumptions
- NEVER delegate without stating which step you're on
- NEVER retry a failed agent—use the fallback instead
- NEVER call tools directly—you have no tools
- ALWAYS transfer final result to parent agent when done`;

// Load settings with fallback
let settings;
try {
  settings = loadSettings();
} catch {
  settings = null;
}

const modelConfig = settings
  ? getModelConfig('planning_agent', settings)
  : { name: 'gemini-2.5-flash', provider: 'gemini' as const, context_length: 128000 };

const customPrompt = settings ? getAgentPrompt('planning_agent', settings) : undefined;

/**
 * Dynamic instruction that includes plan state from session
 */
function getDynamicInstruction(context: InstructionContext): string {
  const currentPlan = (context.state.get('plan') as string) ?? '[]';
  const baseInstruction = customPrompt ?? DEFAULT_INSTRUCTION;
  return baseInstruction.replace('{plan_state}', currentPlan);
}

/**
 * Planning LlmAgent - coordinates specialist agents for complex tasks
 * Uses static specialist agents for module-level instantiation
 */
export const planningAgent = new LlmAgent({
  name: 'planning_agent',
  model: modelConfig.name,
  description: 'Orchestrates multi-step tasks across specialist agents.',
  instruction: getDynamicInstruction,
  afterModelCallback: saveMemoriesOnFinalResponse,
  subAgents: [researchAgent, genericAgent, codeExecutorAgent, chartGeneratorAgent, mcpAgent],
});

/**
 * Creates a planning agent with dynamic MCP tools
 * Use this when you need MCP tools to be fully initialized
 */
export async function createPlanningAgent(
  additionalSubAgents: LlmAgent[] = []
): Promise<LlmAgent> {
  // Get fully initialized MCP agent
  let initializedMcpAgent: LlmAgent;
  try {
    initializedMcpAgent = await createMcpAgent();
  } catch (error) {
    console.warn('MCP agent creation failed, using placeholder:', error);
    initializedMcpAgent = mcpAgent;
  }

  const subAgents: LlmAgent[] = [
    researchAgent,
    genericAgent,
    codeExecutorAgent,
    chartGeneratorAgent,
    initializedMcpAgent,
    ...additionalSubAgents,
  ];

  return new LlmAgent({
    name: 'planning_agent',
    model: modelConfig.name,
    description: 'Orchestrates multi-step tasks across specialist agents.',
    instruction: getDynamicInstruction,
    afterModelCallback: saveMemoriesOnFinalResponse,
    subAgents,
  });
}
