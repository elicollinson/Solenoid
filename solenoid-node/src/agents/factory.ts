/**
 * Agent Factory
 *
 * Creates and wires up the complete agent hierarchy. Establishes the delegation
 * chain: UserProxy → Prime → Planning → Specialists (Research, Code, Chart, MCP, Generic).
 *
 * Agent Hierarchy:
 * - user_proxy_agent: Entry point, quality gates responses before delivery
 * - prime_agent: Routes simple queries vs complex tasks needing delegation
 * - planning_agent: Orchestrates multi-step tasks across specialist agents
 * - Specialists: Domain-specific agents (research, code execution, charts, MCP tools, general text)
 *
 * Provides both async (with MCP) and sync (without MCP) initialization variants.
 */
import type { Agent } from './types.js';
import { AgentRunner } from './runner.js';
import { createUserProxyAgent } from './user-proxy.js';
import { createPrimeAgent } from './prime.js';
import { createPlanningAgent } from './planning.js';
import { createResearchAgent } from './research.js';
import { createGenericAgent } from './generic.js';
import { createCodeExecutorAgent } from './code-executor.js';
import { createChartGeneratorAgent } from './chart-generator.js';
import { createMcpAgent } from './mcp.js';

export interface AgentHierarchy {
  rootAgent: Agent;
  runner: AgentRunner;
}

export async function createAgentHierarchy(): Promise<AgentHierarchy> {
  // Create specialist agents
  const researchAgent = createResearchAgent();
  const genericAgent = createGenericAgent();
  const codeExecutorAgent = createCodeExecutorAgent();
  const chartGeneratorAgent = createChartGeneratorAgent();

  // MCP agent is async due to server connections
  let mcpAgent: Agent | null = null;
  try {
    mcpAgent = await createMcpAgent();
  } catch (error) {
    console.warn('MCP agent creation failed:', error);
  }

  // Build sub-agents list
  const subAgents: Agent[] = [
    researchAgent,
    genericAgent,
    codeExecutorAgent,
    chartGeneratorAgent,
  ];

  if (mcpAgent) {
    subAgents.push(mcpAgent);
  }

  // Create planning agent with specialist sub-agents
  const planningAgent = createPlanningAgent(subAgents);

  // Create prime agent (router)
  const primeAgent = createPrimeAgent(planningAgent);

  // Create user proxy agent (entry point)
  const userProxyAgent = createUserProxyAgent(primeAgent);

  // Create runner
  const runner = new AgentRunner(userProxyAgent);

  return {
    rootAgent: userProxyAgent,
    runner,
  };
}

// Sync version for simpler use cases (without MCP)
export function createAgentHierarchySync(): AgentHierarchy {
  // Create specialist agents
  const researchAgent = createResearchAgent();
  const genericAgent = createGenericAgent();
  const codeExecutorAgent = createCodeExecutorAgent();
  const chartGeneratorAgent = createChartGeneratorAgent();

  const subAgents: Agent[] = [
    researchAgent,
    genericAgent,
    codeExecutorAgent,
    chartGeneratorAgent,
  ];

  // Create planning agent with specialist sub-agents
  const planningAgent = createPlanningAgent(subAgents);

  // Create prime agent (router)
  const primeAgent = createPrimeAgent(planningAgent);

  // Create user proxy agent (entry point)
  const userProxyAgent = createUserProxyAgent(primeAgent);

  // Create runner
  const runner = new AgentRunner(userProxyAgent);

  return {
    rootAgent: userProxyAgent,
    runner,
  };
}
