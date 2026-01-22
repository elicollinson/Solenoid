/**
 * Solenoid Testing Utilities
 *
 * Internal testing infrastructure for the Solenoid terminal UI.
 * Provides mock agents, test harness, and utilities for testing React Ink components.
 */

// Core testing utilities
export { MockAgent, createMockUseAgent } from './mock-agent.js';
export { SolenoidTestHarness } from './test-harness.js';

// Types
export type {
  UIState,
  StructuredFrame,
  ToolCallAssertion,
  ExpectedEventSequence,
  MockAgentResponse,
  TestHarnessConfig,
  CommandResult,
  Message,
  ToolCall,
  MessagePart,
  AgentEvent,
  AgentInterface,
} from './types.js';

// Re-export ink-testing-library for convenience
export { render } from 'ink-testing-library';
