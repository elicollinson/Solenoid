import type { Agent } from './types.js';
import { AgentRunner } from './runner.js';
import { createUserProxyAgent } from './user-proxy.js';
import { createPrimeAgent } from './prime.js';
import { createPlanningAgent } from './planning.js';
import { createResearchAgent } from './research.js';
import { createGenericAgent } from './generic.js';

export interface AgentHierarchy {
  rootAgent: Agent;
  runner: AgentRunner;
}

export function createAgentHierarchy(): AgentHierarchy {
  // Create specialist agents
  const researchAgent = createResearchAgent();
  const genericAgent = createGenericAgent();

  // Create planning agent with specialist sub-agents
  const planningAgent = createPlanningAgent([researchAgent, genericAgent]);

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
