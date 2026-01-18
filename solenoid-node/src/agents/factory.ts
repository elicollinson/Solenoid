/**
 * Agent Factory (ADK)
 *
 * Creates and wires up the complete agent hierarchy. The hierarchy is now
 * established through module-level imports, following the Python pattern.
 * This factory provides backwards-compatible async initialization for
 * cases where MCP tools need to be fully loaded.
 *
 * Agent Hierarchy:
 * - user_proxy_agent: Entry point, quality gates responses before delivery
 * - prime_agent: Routes simple queries vs complex tasks needing delegation
 * - planning_agent: Orchestrates multi-step tasks across specialist agents
 * - Specialists: Domain-specific agents (research, code execution, charts, MCP tools, general text)
 *
 * Dependencies:
 * - @google/adk: LlmAgent for ADK-compatible agents
 */
import type { LlmAgent } from '@google/adk';
import { InMemoryRunner } from '@google/adk';
import { AgentRunner, runner, runAgent, createRunner } from './runner.js';
import { rootAgent, userProxyAgent, createUserProxyAgent } from './user-proxy.js';
import { primeAgent } from './prime.js';
import { planningAgent } from './planning.js';
import { researchAgent } from './research.js';
import { genericAgent } from './generic.js';
import { codeExecutorAgent } from './code-executor.js';
import { chartGeneratorAgent } from './chart-generator.js';
import { mcpAgent } from './mcp.js';

// Re-export all agents for easy access
export {
  rootAgent,
  userProxyAgent,
  primeAgent,
  planningAgent,
  researchAgent,
  genericAgent,
  codeExecutorAgent,
  chartGeneratorAgent,
  mcpAgent,
};

// Re-export runner utilities
export { runner, runAgent, createRunner, AgentRunner };

/**
 * Agent hierarchy interface for backwards compatibility
 */
export interface AgentHierarchy {
  rootAgent: LlmAgent;
  runner: AgentRunner;
}

/**
 * ADK-native agent hierarchy interface
 */
export interface AdkAgentHierarchy {
  rootAgent: LlmAgent;
  runner: InMemoryRunner;
}

/**
 * Creates the agent hierarchy with fully initialized MCP tools
 * This is the recommended async initialization for production use
 *
 * @returns AgentHierarchy with rootAgent and legacy AgentRunner
 */
export async function createAgentHierarchy(): Promise<AgentHierarchy> {
  const initializedRootAgent = await createUserProxyAgent();
  const agentRunner = new AgentRunner(initializedRootAgent);

  return {
    rootAgent: initializedRootAgent,
    runner: agentRunner,
  };
}

/**
 * Creates the ADK-native agent hierarchy with InMemoryRunner
 *
 * @returns AdkAgentHierarchy with rootAgent and ADK InMemoryRunner
 */
export async function createAdkAgentHierarchy(): Promise<AdkAgentHierarchy> {
  const initializedRootAgent = await createUserProxyAgent();
  const adkRunner = new InMemoryRunner({
    agent: initializedRootAgent,
    appName: 'Solenoid',
  });

  return {
    rootAgent: initializedRootAgent,
    runner: adkRunner,
  };
}

/**
 * Synchronous version using module-level agents (without MCP initialization)
 * Use this for simpler use cases where MCP tools are not needed
 *
 * @returns AgentHierarchy with rootAgent and legacy AgentRunner
 */
export function createAgentHierarchySync(): AgentHierarchy {
  return {
    rootAgent,
    runner: new AgentRunner(rootAgent),
  };
}

/**
 * Gets the static module-level agent hierarchy
 * This provides instant access but MCP tools may not be initialized
 */
export function getStaticHierarchy(): AdkAgentHierarchy {
  return {
    rootAgent,
    runner,
  };
}
