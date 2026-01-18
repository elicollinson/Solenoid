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
import { rootAgent, createUserProxyAgent } from './user-proxy.js';

const APP_NAME = 'Solenoid';

/**
 * Module-level runner using the static agent hierarchy
 */
export const runner = new InMemoryRunner({
  agent: rootAgent,
  appName: APP_NAME,
});

/**
 * Creates a runner with fully initialized MCP tools
 * Use this when you need MCP tools to be fully initialized
 */
export async function createRunner(): Promise<InMemoryRunner> {
  const initializedRootAgent = await createUserProxyAgent();
  return new InMemoryRunner({
    agent: initializedRootAgent,
    appName: APP_NAME,
  });
}

/**
 * Creates a Content object from text for use with the runner
 */
function createUserContent(text: string): Content {
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
 * @param sessionId Optional session ID (creates new if not provided)
 * @param customRunner Optional custom runner (uses default if not provided)
 */
export async function* runAgent(
  input: string,
  sessionId?: string,
  customRunner?: InMemoryRunner
): AsyncGenerator<AgentStreamChunk, void, unknown> {
  const activeRunner = customRunner ?? runner;
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
  for await (const event of activeRunner.runAsync({
    userId: 'default_user',
    sessionId: sid,
    newMessage: userMessage,
  })) {
    // Extract text content from event
    if (event.content?.parts) {
      for (const part of event.content.parts) {
        if (part.text) {
          yield { type: 'text', content: part.text };
        }
      }
    }

    // Check for final response
    if (isFinalResponse(event)) {
      yield { type: 'done' };
      return;
    }
  }

  yield { type: 'done' };
}

/**
 * Legacy AgentRunner class for backwards compatibility
 * Wraps the ADK InMemoryRunner with the existing interface
 */
export class AgentRunner {
  private adkRunner: InMemoryRunner;

  constructor(agent?: LlmAgent) {
    this.adkRunner = new InMemoryRunner({
      agent: agent ?? rootAgent,
      appName: APP_NAME,
    });
  }

  async *run(
    input: string,
    sessionId?: string
  ): AsyncGenerator<AgentStreamChunk, void, unknown> {
    yield* runAgent(input, sessionId, this.adkRunner);
  }

  /**
   * Gets the underlying ADK runner
   */
  getAdkRunner(): InMemoryRunner {
    return this.adkRunner;
  }
}
