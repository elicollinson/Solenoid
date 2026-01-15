import type { Agent } from './types.js';
import { AgentRunner } from './runner.js';
import { createUserProxyAgent } from './user-proxy.js';
import { createPrimeAgent } from './prime.js';
import { createPlanningAgent } from './planning.js';

export interface AgentHierarchy {
  rootAgent: Agent;
  runner: AgentRunner;
}

export function createAgentHierarchy(): AgentHierarchy {
  const planningAgent = createPlanningAgent([]);

  const primeAgent = createPrimeAgent(planningAgent);

  const userProxyAgent = createUserProxyAgent(primeAgent);

  const runner = new AgentRunner(userProxyAgent);

  return {
    rootAgent: userProxyAgent,
    runner,
  };
}
