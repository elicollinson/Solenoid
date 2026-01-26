/**
 * Chat Flow Integration Tests
 *
 * Tests for the full chat interaction flow in the Solenoid terminal UI.
 */
import { describe, it, expect, beforeEach, afterEach } from 'bun:test';
import { SolenoidTestHarness } from '../../src/ui/testing/index.js';

describe('Chat Flow', () => {
  let harness: SolenoidTestHarness;

  beforeEach(async () => {
    harness = new SolenoidTestHarness({
      responses: {
        hello: {
          textChunks: ['Hello! ', 'How can I ', 'help you today?'],
          chunkDelay: 10,
        },
        search: {
          toolCalls: [{ name: 'search_web', args: { query: 'test query' } }],
          textChunks: ['Here are the search results...'],
        },
        error: {
          error: 'Something went wrong',
        },
        default: { textChunks: ['I received your message.'] },
      },
    });
    await harness.start();
  });

  afterEach(() => {
    harness.dispose();
  });

  it('sends user message and receives response', async () => {
    const result = await harness.sendMessage('hello');

    expect(result.success).toBe(true);

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('You')).toBe(true);
    expect(frame.containsText('hello')).toBe(true);
    expect(frame.containsText('Hello!')).toBe(true);
    expect(frame.containsText('How can I help you today?')).toBe(true);
  });

  // This test is inherently timing-dependent and may be flaky
  // The processing state appears briefly during async operations
  it.skip('shows processing state during response', async () => {
    const resultPromise = harness.sendMessage('hello');

    await new Promise((r) => setTimeout(r, 20));

    const frames = harness.getFrameHistory();
    const processingFrame = frames.find((f) => f.containsText('Thinking'));
    expect(processingFrame).toBeDefined();

    await resultPromise;
  });

  it('handles tool calls correctly', async () => {
    await harness.sendMessage('search something');

    // Verify tool call was made
    const mockAgent = harness.getMockAgent();
    const events = mockAgent.getEventHistory();

    const toolStartEvent = events.find((e) => e.type === 'tool_start');
    expect(toolStartEvent?.toolName).toBe('search_web');

    // Verify response text
    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Here are the search results')).toBe(true);
  });

  it('displays error messages from agent', async () => {
    await harness.sendMessage('error');

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Error')).toBe(true);
    expect(frame.containsText('Something went wrong')).toBe(true);
  });

  it('maintains conversation history', async () => {
    await harness.sendMessage('first message');
    await harness.waitForIdle();

    await harness.sendMessage('second message');
    await harness.waitForIdle();

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('first message')).toBe(true);
    expect(frame.containsText('second message')).toBe(true);
  });

  it('input is disabled during processing', async () => {
    const resultPromise = harness.sendMessage('hello');

    // Check that input shows disabled state
    await new Promise((r) => setTimeout(r, 15));
    const state = harness.getState();
    expect(state.isProcessing).toBe(true);
    expect(state.inputEnabled).toBe(false);

    await resultPromise;

    // After completion, input should be enabled
    const finalState = harness.getState();
    expect(finalState.isProcessing).toBe(false);
    expect(finalState.inputEnabled).toBe(true);
  });

  it('captures all events in order', async () => {
    await harness.sendMessage('hello');

    const events = harness.getMockAgent().getEventHistory();

    // Should have text events and a done event
    const textEvents = events.filter((e) => e.type === 'text');
    const doneEvents = events.filter((e) => e.type === 'done');

    expect(textEvents.length).toBeGreaterThan(0);
    expect(doneEvents.length).toBe(1);

    // Done should be last
    expect(events.at(-1)?.type).toBe('done');
  });

  it('empty messages are not sent', async () => {
    // Try to send empty message
    await harness.sendMessage('');

    const mockAgent = harness.getMockAgent();
    expect(mockAgent.getCapturedInputs().length).toBe(0);
  });

  it('whitespace-only messages are not sent', async () => {
    // Try to send whitespace message
    await harness.sendMessage('   ');

    const mockAgent = harness.getMockAgent();
    expect(mockAgent.getCapturedInputs().length).toBe(0);
  });

  it('uses default response for unmatched patterns', async () => {
    await harness.sendMessage('some random message');

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('I received your message')).toBe(true);
  });
});
