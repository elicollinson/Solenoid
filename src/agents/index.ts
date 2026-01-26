/**
 * Agents Module (ADK)
 *
 * Exports all agents, types, and utilities for the ADK-based multi-agent system.
 * The agent hierarchy is established through async initialization via
 * createPlanningAgent() which sets up MCP tools.
 *
 * Agent Hierarchy:
 * - planning_agent (root): Orchestrator for complex multi-step tasks
 * - Specialists: research, code_executor, chart_generator, mcp, generic_executor
 */

// Types
export * from './types.js';

// Runner
export { AgentRunner, runAgent, createRunner, createUserContent } from './runner.js';

// Agents - Factory functions for async initialization
export { createPlanningAgent } from './planning.js';

// Module-level agent instances (for sync usage)
export { researchAgent } from './research.js';
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
  createAdkAgentHierarchy,
  type AgentHierarchy,
  type AdkAgentHierarchy,
} from './factory.js';
