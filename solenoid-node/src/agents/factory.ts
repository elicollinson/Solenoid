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

// Register OllamaLlm with ADK's LLMRegistry (side-effect import)
import '../llm/ollama-adk.js';
import { createPlanningAgent } from './planning.js';


/**
 * ADK-native agent hierarchy interface
 */
export interface AdkAgentHierarchy {
  rootAgent: LlmAgent;
  runner: InMemoryRunner;
}

/**
 * Creates the ADK-native agent hierarchy with InMemoryRunner
 *
 * @returns AdkAgentHierarchy with rootAgent and ADK InMemoryRunner
 */
export async function createAdkAgentHierarchy(): Promise<AdkAgentHierarchy> {
  const initializedRootAgent = await createPlanningAgent();
  const adkRunner = new InMemoryRunner({
    agent: initializedRootAgent,
    appName: 'Solenoid',
  });

  return {
    rootAgent: initializedRootAgent,
    runner: adkRunner,
  };
}
