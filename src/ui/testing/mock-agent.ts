/**
 * Mock Agent
 *
 * Provides a controllable agent implementation for testing.
 * Simulates the async generator pattern used by the real useAgent hook.
 */
import type { AgentEvent } from '../hooks/useAgent.js';
import type { MockAgentResponse } from './types.js';

/**
 * MockAgent provides a controllable agent implementation for testing.
 * It simulates the async generator pattern used by the real useAgent hook.
 *
 * @example
 * ```typescript
 * const mockAgent = new MockAgent();
 * mockAgent.setResponse('hello', {
 *   textChunks: ['Hello', ' there!'],
 *   chunkDelay: 10,
 * });
 *
 * for await (const event of mockAgent.run('hello')) {
 *   console.log(event);
 * }
 * ```
 */
export class MockAgent {
  private responses: Map<string, MockAgentResponse> = new Map();
  private defaultResponse: MockAgentResponse = {
    textChunks: ['I am a mock response.'],
  };
  private capturedInputs: string[] = [];
  private eventHistory: AgentEvent[] = [];

  /**
   * Configure a response for a specific input pattern
   */
  setResponse(pattern: string | RegExp, response: MockAgentResponse): this {
    const key = pattern instanceof RegExp ? pattern.source : pattern;
    this.responses.set(key, response);
    return this;
  }

  /**
   * Set the default response for unmatched inputs
   */
  setDefaultResponse(response: MockAgentResponse): this {
    this.defaultResponse = response;
    return this;
  }

  /**
   * Get all inputs that were sent to this mock agent
   */
  getCapturedInputs(): string[] {
    return [...this.capturedInputs];
  }

  /**
   * Get all events that were emitted
   */
  getEventHistory(): AgentEvent[] {
    return [...this.eventHistory];
  }

  /**
   * Clear captured state for test isolation
   */
  reset(): void {
    this.capturedInputs = [];
    this.eventHistory = [];
  }

  /**
   * Clear all configured responses
   */
  clearResponses(): void {
    this.responses.clear();
  }

  /**
   * The run method that matches the useAgent interface
   */
  async *run(input: string): AsyncGenerator<AgentEvent, void, unknown> {
    this.capturedInputs.push(input);

    // Find matching response
    const response = this.findResponse(input);

    // Simulate error if configured
    if (response.error) {
      const errorEvent: AgentEvent = { type: 'error', error: response.error };
      this.eventHistory.push(errorEvent);
      yield errorEvent;
      return;
    }

    // Simulate transfer if configured
    if (response.transferTo) {
      const transferEvent: AgentEvent = {
        type: 'transfer',
        transferTo: response.transferTo,
      };
      this.eventHistory.push(transferEvent);
      yield transferEvent;
    }

    // Emit tool calls with lifecycle events
    if (response.toolCalls) {
      for (const toolCall of response.toolCalls) {
        const toolCallId = crypto.randomUUID();

        // tool_start
        const startEvent: AgentEvent = {
          type: 'tool_start',
          toolCallId,
          toolName: toolCall.name,
        };
        this.eventHistory.push(startEvent);
        yield startEvent;

        // tool_args
        if (toolCall.args) {
          const argsEvent: AgentEvent = {
            type: 'tool_args',
            toolCallId,
            toolArgs: JSON.stringify(toolCall.args),
          };
          this.eventHistory.push(argsEvent);
          yield argsEvent;
        }

        // Simulate execution time
        if (toolCall.duration) {
          await this.delay(toolCall.duration);
        }

        // tool_end
        const endEvent: AgentEvent = {
          type: 'tool_end',
          toolCallId,
        };
        this.eventHistory.push(endEvent);
        yield endEvent;
      }
    }

    // Emit text chunks
    if (response.textChunks) {
      for (const chunk of response.textChunks) {
        if (response.chunkDelay) {
          await this.delay(response.chunkDelay);
        }
        const textEvent: AgentEvent = { type: 'text', content: chunk };
        this.eventHistory.push(textEvent);
        yield textEvent;
      }
    }

    // Final done event
    const doneEvent: AgentEvent = { type: 'done' };
    this.eventHistory.push(doneEvent);
    yield doneEvent;
  }

  private findResponse(input: string): MockAgentResponse {
    for (const [pattern, response] of this.responses) {
      if (input.includes(pattern) || new RegExp(pattern).test(input)) {
        return response;
      }
    }
    return this.defaultResponse;
  }

  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

/**
 * Factory to create a mock useAgent hook
 */
export function createMockUseAgent(mockAgent: MockAgent) {
  return function useAgent() {
    return {
      run: (input: string) => mockAgent.run(input),
    };
  };
}
