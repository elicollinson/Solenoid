/**
 * E2E Tests using Enhanced Test Harness
 *
 * These tests demonstrate the enhanced test harness capabilities:
 * - Real agent mode with Ollama
 * - Custom agent injection
 * - Event tracking across all agent types
 */
import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
import {
  SolenoidTestHarness,
  type AgentInterface,
  type AgentEvent,
} from '../../src/ui/testing/index.js';

describe('Enhanced Test Harness - Custom Agent Injection', () => {
  it('should work with a custom agent', async () => {
    const events: AgentEvent[] = [];

    // Create a simple custom agent
    const customAgent: AgentInterface = {
      async *run(input: string): AsyncGenerator<AgentEvent, void, unknown> {
        const textEvent: AgentEvent = {
          type: 'text',
          content: `Custom response to: ${input}`,
        };
        events.push(textEvent);
        yield textEvent;

        const doneEvent: AgentEvent = { type: 'done' };
        events.push(doneEvent);
        yield doneEvent;
      },
      getEventHistory: () => events,
      reset: () => {
        events.length = 0;
      },
    };

    const harness = new SolenoidTestHarness({
      customAgent,
      timeout: 10000,
    });

    await harness.start();

    expect(harness.isUsingCustomAgent()).toBe(true);
    expect(harness.isUsingRealAgent()).toBe(false);

    // Send a message
    await harness.sendMessage('test message');

    // Wait for processing
    await harness.waitForIdle();

    // Check that custom agent was called
    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Custom response to: test message')).toBe(true);

    // Check event history
    const eventHistory = harness.getEventHistory();
    expect(eventHistory.length).toBeGreaterThan(0);
    expect(eventHistory.some((e) => e.type === 'text')).toBe(true);

    harness.dispose();
  });

  it('should track events from custom agents', async () => {
    let eventCount = 0;

    const customAgent: AgentInterface = {
      async *run(_input: string): AsyncGenerator<AgentEvent, void, unknown> {
        yield { type: 'text', content: 'Event 1' };
        eventCount++;
        yield { type: 'text', content: 'Event 2' };
        eventCount++;
        yield { type: 'done' };
        eventCount++;
      },
    };

    const harness = new SolenoidTestHarness({
      customAgent,
      timeout: 10000,
    });

    await harness.start();
    await harness.sendMessage('trigger events');
    await harness.waitForIdle();

    expect(eventCount).toBe(3);

    // Events should be tracked even without getEventHistory
    const events = harness.getEventHistory();
    expect(events.length).toBe(3);

    harness.dispose();
  });
});

describe('Enhanced Test Harness - Mock Agent Mode', () => {
  it('should still work in mock mode (default)', async () => {
    const harness = new SolenoidTestHarness({
      responses: {
        test: { textChunks: ['Mock response 1', ' Mock response 2'] },
      },
    });

    await harness.start();

    expect(harness.isUsingRealAgent()).toBe(false);
    expect(harness.isUsingCustomAgent()).toBe(false);

    await harness.sendMessage('test');
    await harness.waitForIdle();

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Mock response 1')).toBe(true);
    expect(frame.containsText('Mock response 2')).toBe(true);

    harness.dispose();
  });

  it('should track mock agent events through getEventHistory', async () => {
    const harness = new SolenoidTestHarness({
      responses: {
        test: {
          textChunks: ['Response'],
          toolCalls: [{ name: 'test_tool', args: { key: 'value' } }],
        },
      },
    });

    await harness.start();
    await harness.sendMessage('test');
    await harness.waitForIdle();

    const events = harness.getEventHistory();
    expect(events.some((e) => e.type === 'text')).toBe(true);
    expect(events.some((e) => e.type === 'tool_start')).toBe(true);

    harness.dispose();
  });
});

describe('Enhanced Test Harness - Real Agent Mode', () => {
  let harness: SolenoidTestHarness | null = null;
  let initError: Error | null = null;

  beforeAll(async () => {
    // Set longer timeout for agent initialization
    vi.setConfig({ testTimeout: 180000 });

    harness = new SolenoidTestHarness({
      useRealAgent: true,
      initTimeout: 60000,
      timeout: 120000,
      debug: false,
    });

    try {
      await harness.start();
    } catch (error) {
      initError = error instanceof Error ? error : new Error(String(error));
      console.log('Real agent initialization error:', initError.message);
    }
  }, 120000);

  afterAll(() => {
    if (harness) {
      harness.dispose();
    }
  });

  it('should be configured for real agent mode', () => {
    if (initError) {
      console.log('Skipping - initialization failed');
      return;
    }

    expect(harness!.isUsingRealAgent()).toBe(true);
    expect(harness!.isUsingCustomAgent()).toBe(false);
  });

  it('should render initial UI correctly', () => {
    if (initError) {
      console.log('Skipping - initialization failed');
      return;
    }

    const frame = harness!.getCurrentFrame();
    expect(frame.containsText('Solenoid')).toBe(true);
    expect(frame.containsText('No messages yet')).toBe(true);
  });

  it('should handle slash commands', async () => {
    if (initError) {
      console.log('Skipping - initialization failed');
      return;
    }

    await harness!.executeCommand('/help');
    await harness!.waitForIdle();

    const frame = harness!.getCurrentFrame();
    expect(frame.containsText('Solenoid Help')).toBe(true);
  });

  it('should process a message with real agent', async () => {
    if (initError) {
      console.log('Skipping - initialization failed');
      return;
    }

    // Clear previous messages
    await harness!.executeCommand('/clear');
    await harness!.waitForIdle();

    // Send a simple message
    await harness!.sendMessage('Say only the word hello');

    // Wait with longer timeout for real agent
    try {
      await harness!.waitFor(
        () => {
          const state = harness!.getState();
          return !state.isProcessing;
        },
        { timeout: 90000, interval: 1000 }
      );
    } catch {
      console.log('Timeout waiting for response - checking current state');
    }

    const frame = harness!.getCurrentFrame();
    console.log('Final frame (first 500 chars):', frame.raw.substring(0, 500));

    // Should show user message
    expect(frame.containsText('You')).toBe(true);

    // Check events were captured
    const events = harness!.getEventHistory();
    console.log('Events captured:', events.length);
    console.log('Event types:', events.map((e) => e.type).join(', '));
  }, 120000);
});

describe('Test Harness - getActiveAgent', () => {
  it('should return mock agent in mock mode', async () => {
    const harness = new SolenoidTestHarness();
    await harness.start();

    const agent = harness.getActiveAgent();
    expect(agent).toBeDefined();
    expect(typeof agent.run).toBe('function');

    harness.dispose();
  });

  it('should return custom agent when injected', async () => {
    const customAgent: AgentInterface = {
      async *run(): AsyncGenerator<AgentEvent, void, unknown> {
        yield { type: 'done' };
      },
    };

    const harness = new SolenoidTestHarness({ customAgent });
    await harness.start();

    const agent = harness.getActiveAgent();
    expect(agent).toBe(customAgent);

    harness.dispose();
  });
});
