/**
 * Agent Type Definitions
 *
 * Core TypeScript interfaces and types for the ADK-based multi-agent system.
 * Provides both ADK-compatible types and backwards-compatible types for
 * existing code that uses the AgentStreamChunk pattern.
 *
 * Dependencies:
 * - @google/adk: LlmAgent, CallbackContext for ADK agent types
 */
import type { LlmAgent, CallbackContext, LlmRequest, LlmResponse } from '@google/adk';

// Re-export ADK types for convenience
export type { LlmAgent, CallbackContext, LlmRequest, LlmResponse };

/**
 * ADK callback function type for beforeModelCallback
 */
export type AdkBeforeModelCallback = (params: {
  context: CallbackContext;
  request: LlmRequest;
}) => Promise<LlmResponse | undefined> | LlmResponse | undefined;

/**
 * ADK callback function type for afterModelCallback
 */
export type AdkAfterModelCallback = (params: {
  context: CallbackContext;
  response: LlmResponse;
}) => Promise<LlmResponse | undefined> | LlmResponse | undefined;

/**
 * Backwards-compatible stream chunk type for server API responses
 */
export interface AgentStreamChunk {
  type: 'text' | 'tool_call' | 'tool_result' | 'transfer' | 'done';
  content?: string;
  toolCall?: {
    function: {
      name: string;
      arguments: Record<string, unknown>;
    };
  };
  toolResult?: { name: string; result: string };
  transferTo?: string;
}

/**
 * Backwards-compatible async generator type for streaming responses
 */
export type AgentStreamResponse = AsyncGenerator<AgentStreamChunk, void, unknown>;

/**
 * Session state interface for storing context across agent calls
 */
export interface SessionState {
  originalUserQuery?: string;
  plan?: string;
  userId?: string;
  appName?: string;
  loadedMemories?: unknown[];
  memoryContext?: string;
  [key: string]: unknown;
}

/**
 * Agent runner interface for backwards compatibility
 */
export interface AgentRunner {
  run(
    input: string,
    sessionId?: string
  ): AsyncGenerator<AgentStreamChunk, void, unknown>;
}
