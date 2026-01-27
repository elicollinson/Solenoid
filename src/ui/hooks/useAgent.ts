import type { InMemoryRunner } from '@google/adk';
/**
 * useAgent Hook
 *
 * Provides direct ADK integration for the Ink UI using React 18 Suspense.
 * Uses a resource pattern to suspend until MCP tools are loaded.
 */
import { useCallback, useRef } from 'react';
import { createAdkAgentHierarchy, runAgent } from '../../agents/index.js';

export interface AgentEvent {
  type: 'text' | 'tool_start' | 'tool_args' | 'tool_end' | 'transfer' | 'done' | 'error';
  content?: string;
  toolCallId?: string;
  toolName?: string;
  toolArgs?: string;
  transferTo?: string;
  error?: string;
}

/**
 * Resource wrapper for Suspense compatibility.
 * Throws the promise while pending, returns result when resolved.
 */
function createResource<T>(promise: Promise<T>) {
  let status: 'pending' | 'success' | 'error' = 'pending';
  let result: T;
  let error: Error;

  const suspender = promise.then(
    (r) => {
      status = 'success';
      result = r;
    },
    (e) => {
      status = 'error';
      error = e instanceof Error ? e : new Error(String(e));
    }
  );

  return {
    read(): T {
      if (status === 'pending') throw suspender;
      if (status === 'error') throw error;
      return result;
    },
  };
}

// Singleton resource created at module level
let agentResource: ReturnType<typeof createResource<InMemoryRunner>> | null = null;

function getAgentResource() {
  if (!agentResource) {
    agentResource = createResource(createAdkAgentHierarchy().then(({ runner }) => runner));
  }
  return agentResource;
}

export function useAgent() {
  // This will suspend if runner not ready
  const runner = getAgentResource().read();
  const sessionIdRef = useRef<string>(crypto.randomUUID());

  const run = useCallback(
    async function* (input: string): AsyncGenerator<AgentEvent, void, unknown> {
      try {
        for await (const chunk of runAgent(input, runner, sessionIdRef.current)) {
          switch (chunk.type) {
            case 'text':
              if (chunk.content) {
                yield { type: 'text', content: chunk.content };
              }
              break;
            case 'tool_call':
              if (chunk.toolCall) {
                const toolCallId = crypto.randomUUID();
                yield {
                  type: 'tool_start',
                  toolCallId,
                  toolName: chunk.toolCall.function.name,
                };
                if (chunk.toolCall.function.arguments) {
                  yield {
                    type: 'tool_args',
                    toolCallId,
                    toolArgs: JSON.stringify(chunk.toolCall.function.arguments),
                  };
                }
                yield { type: 'tool_end', toolCallId };
              }
              break;
            case 'transfer':
              if (chunk.transferTo) {
                yield { type: 'transfer', transferTo: chunk.transferTo };
              }
              break;
            case 'done':
              yield { type: 'done' };
              break;
          }
        }
      } catch (error) {
        yield {
          type: 'error',
          error: error instanceof Error ? error.message : String(error),
        };
      }
    },
    [runner]
  );

  return { run };
}
