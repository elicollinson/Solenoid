/**
 * AG-UI Protocol Encoder
 *
 * Provides utilities for encoding events according to the AG-UI protocol
 * using the official @ag-ui/core package types and schemas.
 *
 * This module bridges the gap between the internal agent system and
 * AG-UI compliant event streaming.
 */
import { EventType } from '@ag-ui/core';

/**
 * AG-UI Event types for SSE streaming
 */
export { EventType };

/**
 * Create a RUN_STARTED event
 */
export function createRunStartedEvent(runId: string, threadId: string) {
  return {
    type: EventType.RUN_STARTED,
    runId,
    threadId,
    timestamp: Date.now(),
  };
}

/**
 * Create a RUN_FINISHED event
 */
export function createRunFinishedEvent(runId: string) {
  return {
    type: EventType.RUN_FINISHED,
    runId,
    timestamp: Date.now(),
  };
}

/**
 * Create a RUN_ERROR event
 */
export function createRunErrorEvent(runId: string, message: string, code?: string) {
  return {
    type: EventType.RUN_ERROR,
    runId,
    message,
    code,
    timestamp: Date.now(),
  };
}

/**
 * Create a TEXT_MESSAGE_START event
 */
export function createTextMessageStartEvent(
  messageId: string,
  role: 'assistant' | 'user' = 'assistant'
) {
  return {
    type: EventType.TEXT_MESSAGE_START,
    messageId,
    role,
    timestamp: Date.now(),
  };
}

/**
 * Create a TEXT_MESSAGE_CONTENT event
 */
export function createTextMessageContentEvent(messageId: string, delta: string) {
  return {
    type: EventType.TEXT_MESSAGE_CONTENT,
    messageId,
    delta,
    timestamp: Date.now(),
  };
}

/**
 * Create a TEXT_MESSAGE_END event
 */
export function createTextMessageEndEvent(messageId: string) {
  return {
    type: EventType.TEXT_MESSAGE_END,
    messageId,
    timestamp: Date.now(),
  };
}

/**
 * Create a TOOL_CALL_START event
 * AG-UI protocol requires tool call ID, name, and optionally the parent message ID
 */
export function createToolCallStartEvent(
  toolCallId: string,
  toolName: string,
  parentMessageId?: string
) {
  return {
    type: EventType.TOOL_CALL_START,
    toolCallId,
    toolName,
    parentMessageId,
    timestamp: Date.now(),
  };
}

/**
 * Create a TOOL_CALL_ARGS event for streaming tool arguments
 */
export function createToolCallArgsEvent(toolCallId: string, delta: string) {
  return {
    type: EventType.TOOL_CALL_ARGS,
    toolCallId,
    delta,
    timestamp: Date.now(),
  };
}

/**
 * Create a TOOL_CALL_END event
 */
export function createToolCallEndEvent(toolCallId: string) {
  return {
    type: EventType.TOOL_CALL_END,
    toolCallId,
    timestamp: Date.now(),
  };
}

/**
 * Create a TOOL_CALL_RESULT event
 */
export function createToolCallResultEvent(toolCallId: string, result: string, error?: string) {
  return {
    type: EventType.TOOL_CALL_RESULT,
    toolCallId,
    result,
    error,
    timestamp: Date.now(),
  };
}

/**
 * Create a STATE_SNAPSHOT event for agent state synchronization
 */
export function createStateSnapshotEvent(state: Record<string, unknown>) {
  return {
    type: EventType.STATE_SNAPSHOT,
    state,
    timestamp: Date.now(),
  };
}

/**
 * Create a STATE_DELTA event for incremental state updates
 */
export function createStateDeltaEvent(delta: Array<{ op: string; path: string; value?: unknown }>) {
  return {
    type: EventType.STATE_DELTA,
    delta,
    timestamp: Date.now(),
  };
}

/**
 * Create a CUSTOM event for application-specific data
 * Used for chart rendering and other UI-specific events
 */
export function createCustomEvent(name: string, value: unknown) {
  return {
    type: EventType.CUSTOM,
    name,
    value,
    timestamp: Date.now(),
  };
}

/**
 * Encode an event for SSE transmission
 */
export function encodeSSEEvent(event: { type: EventType } & Record<string, unknown>): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

/**
 * Convert internal tool call to AG-UI format
 */
export function toAgUiToolCall(toolCallId: string, name: string, args: Record<string, unknown>) {
  return {
    id: toolCallId,
    type: 'function' as const,
    function: {
      name,
      arguments: JSON.stringify(args),
    },
  };
}
