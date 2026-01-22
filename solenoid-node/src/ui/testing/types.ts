/**
 * Testing Types
 *
 * Type definitions for the Solenoid testing infrastructure.
 */
import type { Message, ToolCall, MessagePart } from '../components/index.js';
import type { AgentEvent } from '../hooks/useAgent.js';

/**
 * Structured representation of the current UI state.
 * Enables programmatic validation without string parsing.
 */
export interface UIState {
  screen: 'chat' | 'settings' | 'help' | 'loading' | 'error';
  messages: Message[];
  isProcessing: boolean;
  status: string;
  inputValue: string;
  inputEnabled: boolean;
}

/**
 * Structured representation of a rendered frame.
 * Captures both raw terminal output and parsed structure.
 */
export interface StructuredFrame {
  /** Raw terminal output string */
  raw: string;
  /** Frame capture timestamp */
  timestamp: number;
  /** Parsed UI state (best-effort) */
  ui: Partial<UIState>;
  /** Check if frame contains specific text */
  containsText: (text: string) => boolean;
  /** Check if frame matches a regex pattern */
  containsPattern: (pattern: RegExp) => boolean;
}

/**
 * Tool call assertion helpers
 */
export interface ToolCallAssertion {
  id?: string;
  name: string;
  expectedStatus: ToolCall['status'];
  expectedArgs?: Record<string, unknown>;
}

/**
 * Event sequence for validating streaming behavior
 */
export interface ExpectedEventSequence {
  events: Array<{
    type: AgentEvent['type'];
    match?: Partial<AgentEvent>;
  }>;
  timeout?: number;
}

/**
 * Mock agent response configuration
 */
export interface MockAgentResponse {
  /** Text chunks to emit (will be yielded as separate text events) */
  textChunks?: string[];

  /** Tool calls to simulate */
  toolCalls?: Array<{
    name: string;
    args?: Record<string, unknown>;
    /** Duration in ms to simulate tool execution */
    duration?: number;
    /** Simulate an error for this tool call */
    error?: string;
  }>;

  /** Delay between chunks in ms */
  chunkDelay?: number;

  /** Simulate agent transfer */
  transferTo?: string;

  /** Simulate an error */
  error?: string;
}

/**
 * Test harness configuration
 */
export interface TestHarnessConfig {
  /** Mock agent responses (keyed by input pattern or 'default') */
  responses?: Record<string, MockAgentResponse>;

  /** Initial messages to pre-populate */
  initialMessages?: Message[];

  /** Start on a specific screen */
  initialScreen?: UIState['screen'];

  /** Custom timeout for async operations */
  timeout?: number;

  /** Enable debug logging */
  debug?: boolean;
}

/**
 * Command result from harness operations
 */
export interface CommandResult {
  success: boolean;
  frames: StructuredFrame[];
  finalState: UIState;
  events: AgentEvent[];
  error?: Error;
}

// Re-export commonly used types
export type { Message, ToolCall, MessagePart, AgentEvent };
