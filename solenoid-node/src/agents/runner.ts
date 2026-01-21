/**
 * Agent Runner (ADK)
 *
 * Session manager that orchestrates agent execution using ADK's InMemoryRunner.
 * Maintains conversation history per session, transforms user input into agent
 * requests, and streams responses back. Acts as the interface between the
 * server API and the ADK-based agent system.
 *
 * Features:
 * - ADK InMemoryRunner for session management
 * - Async generator interface for response streaming (backwards compatible)
 * - Session-based conversation tracking with unique session IDs
 *
 * Dependencies:
 * - @google/adk: InMemoryRunner for session-based agent execution
 * - @google/genai: Content type for message formatting
 */
import { InMemoryRunner, isFinalResponse } from '@google/adk';
import type { LlmAgent } from '@google/adk';
import type { Content } from '@google/genai';
import type { AgentStreamChunk } from './types.js';
import { createPlanningAgent } from './planning.js';
import { agentLogger } from '../utils/logger.js';

const APP_NAME = 'Solenoid';

/**
 * Debug: Log the agent hierarchy
 */
export function logAgentHierarchy(agent: LlmAgent, indent = 0) {
  const prefix = '  '.repeat(indent);
  agentLogger.debug(`${prefix}[Agent] ${agent.name} (model: ${agent.model})`);
  if (agent.subAgents && agent.subAgents.length > 0) {
    for (const subAgent of agent.subAgents) {
      logAgentHierarchy(subAgent as LlmAgent, indent + 1);
    }
  }
}

/**
 * Creates a runner with fully initialized MCP tools
 * Use this when you need MCP tools to be fully initialized
 */
export async function createRunner(): Promise<InMemoryRunner> {
  const initializedRootAgent = await createPlanningAgent();
  return new InMemoryRunner({
    agent: initializedRootAgent,
    appName: APP_NAME,
  });
}

/**
 * Creates a Content object from text for use with the runner
 */
export function createUserContent(text: string): Content {
  return {
    role: 'user',
    parts: [{ text }],
  };
}

/**
 * Runs the agent with the given input and yields stream chunks
 * Compatible with the existing server API
 *
 * @param input User message
 * @param runner The InMemoryRunner to use
 * @param sessionId Optional session ID (creates new if not provided)
 */
export async function* runAgent(
  input: string,
  runner: InMemoryRunner,
  sessionId?: string
): AsyncGenerator<AgentStreamChunk, void, unknown> {
  const activeRunner = runner;
  const sid = sessionId ?? crypto.randomUUID();

  // Try to get existing session, or create a new one
  let session = await activeRunner.sessionService.getSession({
    appName: APP_NAME,
    userId: 'default_user',
    sessionId: sid,
  });

  if (!session) {
    session = await activeRunner.sessionService.createSession({
      appName: APP_NAME,
      userId: 'default_user',
      sessionId: sid,
    });
  }

  // Create user message
  const userMessage = createUserContent(input);

  // Run the agent and stream responses
  try {
    let eventIndex = 0;
    for await (const event of activeRunner.runAsync({
      userId: 'default_user',
      sessionId: sid,
      newMessage: userMessage,
    })) {
      eventIndex++;
      agentLogger.debug(`[Runner] ===== EVENT #${eventIndex} =====`);
      agentLogger.debug(`[Runner] Event ID: ${event.id}, from ${event.author}, parts: ${event.content?.parts?.length ?? 0}, role: ${event.content?.role}, isFinal: ${isFinalResponse(event)}, transferToAgent: ${event.actions?.transferToAgent ?? 'none'}`);

      // Highlight if this event has a transfer action
      if (event.actions?.transferToAgent) {
        agentLogger.debug(`[Runner] *** TRANSFER DETECTED: ${event.author} -> ${event.actions.transferToAgent} ***`);
      }

      // Log what type of parts this event has
      const partTypes = event.content?.parts?.map((p) => {
        if ('text' in p && p.text) return 'text';
        if ('functionCall' in p && p.functionCall) return `functionCall:${p.functionCall.name}`;
        if ('functionResponse' in p && p.functionResponse) return `functionResponse:${(p.functionResponse as { name?: string }).name}`;
        return `unknown(${Object.keys(p).join(',')})`;
      }).join(', ') ?? 'no parts';
      agentLogger.debug(`[Runner] Event parts: ${partTypes}`);

      // If this is a function response, log details
      if (event.content?.parts?.some((p) => 'functionResponse' in p)) {
        agentLogger.debug(`[Runner] Function response event detected!`);
      }

      // Extract text content from event
      if (event.content?.parts) {
        for (const part of event.content.parts) {
          if (part.text) {
            yield { type: 'text', content: part.text };
          }
          // Yield tool calls
          if ('functionCall' in part && part.functionCall?.name) {
            agentLogger.debug(`[Runner] Tool call: ${part.functionCall.name}, args: ${JSON.stringify(part.functionCall.args)}`);
            yield {
              type: 'tool_call',
              toolCall: {
                function: {
                  name: part.functionCall.name,
                  arguments: part.functionCall.args as Record<string, unknown>,
                },
              },
            };
          }
        }
      }

      // Check for final response
      // Note: ADK may yield empty "auth" events that appear final but aren't meaningful
      // Skip these and continue to the next event
      if (isFinalResponse(event)) {
        const hasContent =
          (event.content?.parts?.length ?? 0) > 0 ||
          event.actions?.transferToAgent;
        if (hasContent) {
          agentLogger.debug(`[Runner] Final response received from ${event.author}`);
          yield { type: 'done' };
          return;
        } else {
          agentLogger.debug(`[Runner] Skipping empty final event, continuing...`);
          continue;
        }
      }
    }

    agentLogger.debug(`[Runner] Loop completed without final response`);
    yield { type: 'done' };
  } catch (error) {
    agentLogger.error({ error }, `[Runner] Error during agent execution`);
    yield { type: 'text', content: `Error: ${error instanceof Error ? error.message : String(error)}` };
    yield { type: 'done' };
  }
}

/**
 * Legacy AgentRunner class for backwards compatibility
 * Wraps the ADK InMemoryRunner with the existing interface
 */
export class AgentRunner {
  private adkRunner: InMemoryRunner;

  constructor(agent: LlmAgent) {
    this.adkRunner = new InMemoryRunner({
      agent,
      appName: APP_NAME,
    });
  }

  async *run(
    input: string,
    sessionId?: string
  ): AsyncGenerator<AgentStreamChunk, void, unknown> {
    yield* runAgent(input, this.adkRunner, sessionId);
  }

  /**
   * Gets the underlying ADK runner
   */
  getAdkRunner(): InMemoryRunner {
    return this.adkRunner;
  }
}
