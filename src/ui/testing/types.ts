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
 * Agent interface for test harness compatibility.
 * Both MockAgent and real agents can implement this interface.
 */
export interface AgentInterface {
  /** Run the agent with given input and yield events */
  run(input: string): AsyncGenerator<AgentEvent, void, unknown>;
  /** Get the event history (optional for real agents) */
  getEventHistory?(): AgentEvent[];
  /** Reset the agent state (optional) */
  reset?(): void;
}

/**
 * Settings generation configuration for test harness
 */
export interface SettingsConfig {
  /**
   * If true, automatically generate app_settings.yaml with env vars injected.
   * @default false
   */
  generateSettings?: boolean;

  /**
   * Path to write the generated settings file.
   * @default './app_settings.yaml'
   */
  settingsPath?: string;

  /**
   * Base settings to merge with generated settings.
   * Useful for overriding defaults.
   */
  baseSettings?: Record<string, unknown>;

  /**
   * Additional custom env var mappings.
   * Format: { ENV_VAR_NAME: { settingsPath: ['path', 'to', 'field'], value: 'value' } }
   */
  additionalEnvVars?: Record<string, { settingsPath: string[]; value: string }>;

  /**
   * If true, only include values for env vars that are actually set.
   * If false, include all default settings.
   * @default false
   */
  onlySetEnvVars?: boolean;
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

  /**
   * Use real Ollama agent instead of mock.
   * Requires Ollama to be running with appropriate model.
   * @default false
   */
  useRealAgent?: boolean;

  /**
   * Custom agent to use instead of mock or real agent.
   * Allows injecting any agent that implements AgentInterface.
   */
  customAgent?: AgentInterface;

  /**
   * Initialization timeout for real agent (ms).
   * @default 30000
   */
  initTimeout?: number;

  /**
   * Settings generation configuration.
   * If provided with generateSettings: true, the harness will auto-generate
   * app_settings.yaml with secrets loaded from environment variables.
   */
  settings?: SettingsConfig;
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
