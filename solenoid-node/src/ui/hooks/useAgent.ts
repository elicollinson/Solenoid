/**
 * useAgent Hook
 *
 * Provides direct ADK integration for the Ink UI. Handles:
 * - Async initialization with loading state
 * - Running agents and yielding UI-compatible events
 * - Session management
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import type { InMemoryRunner } from '@google/adk';
import { createAdkAgentHierarchy, runAgent } from '../../agents/index.js';

export type AgentStatus = 'initializing' | 'ready' | 'running' | 'error';

export interface UseAgentOptions {
  onInitError?: (error: Error) => void;
}

export interface AgentEvent {
  type:
    | 'text'
    | 'tool_start'
    | 'tool_args'
    | 'tool_end'
    | 'transfer'
    | 'done'
    | 'error';
  // Text content
  content?: string;
  // Tool call info
  toolCallId?: string;
  toolName?: string;
  toolArgs?: string;
  // Transfer info
  transferTo?: string;
  // Error
  error?: string;
}

export function useAgent(options: UseAgentOptions = {}) {
  const [status, setStatus] = useState<AgentStatus>('initializing');
  const [initError, setInitError] = useState<Error | null>(null);
  const runnerRef = useRef<InMemoryRunner | null>(null);
  const sessionIdRef = useRef<string>(crypto.randomUUID());

  // Initialize runner on mount
  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const { runner } = await createAdkAgentHierarchy();
        if (!cancelled) {
          runnerRef.current = runner;
          setStatus('ready');
        }
      } catch (error) {
        if (!cancelled) {
          const err = error instanceof Error ? error : new Error(String(error));
          setInitError(err);
          setStatus('error');
          options.onInitError?.(err);
        }
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, []);

  // Run agent and yield events
  const run = useCallback(
    async function* (input: string): AsyncGenerator<AgentEvent, void, unknown> {
      if (!runnerRef.current) {
        yield { type: 'error', error: 'Agent not initialized' };
        return;
      }

      setStatus('running');

      try {
        for await (const chunk of runAgent(
          input,
          runnerRef.current,
          sessionIdRef.current
        )) {
          // Transform AgentStreamChunk to AgentEvent
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
      } finally {
        setStatus('ready');
      }
    },
    []
  );

  return {
    status,
    initError,
    run,
    isInitializing: status === 'initializing',
    isReady: status === 'ready',
    isRunning: status === 'running',
  };
}
