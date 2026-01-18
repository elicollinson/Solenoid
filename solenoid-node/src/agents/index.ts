/**
 * Agents Module (ADK)
 *
 * Exports all agents, types, and utilities for the ADK-based multi-agent system.
 * The agent hierarchy is established through module-level instantiation,
 * following the Python source pattern.
 *
 * Agent Hierarchy:
 * - user_proxy_agent (rootAgent): Gateway between user and agent system
 * - prime_agent: Intelligent router for direct answers vs delegation
 * - planning_agent: Orchestrator for complex multi-step tasks
 * - Specialists: research, code_executor, chart_generator, mcp, generic_executor
 */

// Types
export * from './types.js';

// Runner
export { AgentRunner, runner, runAgent, createRunner } from './runner.js';

// Agents - Module-level instances
export { rootAgent, userProxyAgent, createUserProxyAgent } from './user-proxy.js';
export { primeAgent, createPrimeAgent } from './prime.js';
export { planningAgent, createPlanningAgent } from './planning.js';
export { researchAgent, createResearchAgent, researchToolExecutors } from './research.js';
export { genericAgent, createGenericAgent } from './generic.js';
export {
  codeExecutorAgent,
  createCodeExecutorAgent,
  executeCode,
  codeExecutorToolExecutors,
} from './code-executor.js';
export {
  chartGeneratorAgent,
  createChartGeneratorAgent,
  chartGeneratorToolExecutors,
} from './chart-generator.js';
export { mcpAgent, createMcpAgent, mcpToolExecutors } from './mcp.js';

// Factory
export {
  createAgentHierarchy,
  createAgentHierarchySync,
  createAdkAgentHierarchy,
  getStaticHierarchy,
  type AgentHierarchy,
  type AdkAgentHierarchy,
} from './factory.js';
