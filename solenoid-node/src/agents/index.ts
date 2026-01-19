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

export { createUserContent } from './runner.js'

// Factory
export {
  createAdkAgentHierarchy,
  type AgentHierarchy,
  type AdkAgentHierarchy,
} from './factory.js';
