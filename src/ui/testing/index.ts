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
  SettingsConfig,
} from './types.js';

// Re-export config generator for direct access
export {
  generateSettings,
  writeSettingsFile,
  getEnvVarStatus,
  getDefaultSettings,
  DEFAULT_ENV_MAPPINGS,
  type EnvMapping,
  type GenerateSettingsOptions,
  type WriteSettingsOptions,
} from '../../config/generator.js';

// Re-export ink-testing-library for convenience
export { render } from 'ink-testing-library';
