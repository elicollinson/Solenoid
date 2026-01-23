/**
 * Tool Call Lifecycle Integration Tests
 *
 * Tests for tool call state transitions and event handling.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { SolenoidTestHarness } from '../../src/ui/testing/index.js';

describe('Tool Call Lifecycle', () => {
  let harness: SolenoidTestHarness;

  beforeEach(async () => {
    harness = new SolenoidTestHarness({
      responses: {
        chart: {
          toolCalls: [
            {
              name: 'render_chart',
              args: {
                chartType: 'bar',
                title: 'Test Chart',
                data: [
                  { label: 'A', value: 10 },
                  { label: 'B', value: 20 },
                ],
              },
              duration: 50, // Simulate 50ms execution
            },
          ],
          textChunks: ['Here is your chart.'],
        },
        'multi-tool': {
          toolCalls: [
            { name: 'search_web', args: { query: 'test' }, duration: 30 },
            { name: 'execute_code', args: { code: 'print(1)' }, duration: 30 },
          ],
          textChunks: ['Both tools completed.'],
        },
        'tool-only': {
          toolCalls: [{ name: 'read_file', args: { path: '/tmp/test.txt' } }],
        },
        default: { textChunks: ['Default response'] },
      },
    });
    await harness.start();
  });

  afterEach(() => {
    harness.dispose();
  });

  it('emits tool lifecycle events in correct order', async () => {
    await harness.sendMessage('chart');

    const events = harness.getMockAgent().getEventHistory();

    // Find all tool-related events
    const toolStart = events.filter((e) => e.type === 'tool_start');
    const toolArgs = events.filter((e) => e.type === 'tool_args');
    const toolEnd = events.filter((e) => e.type === 'tool_end');

    expect(toolStart).toHaveLength(1);
    expect(toolArgs).toHaveLength(1);
    expect(toolEnd).toHaveLength(1);

    // Verify order: start comes before end
    const startIndex = events.findIndex((e) => e.type === 'tool_start');
    const endIndex = events.findIndex((e) => e.type === 'tool_end');
    expect(startIndex).toBeLessThan(endIndex);
  });

  it('handles multiple sequential tool calls', async () => {
    await harness.sendMessage('multi-tool');

    const events = harness.getMockAgent().getEventHistory();

    const toolStarts = events.filter((e) => e.type === 'tool_start');
    expect(toolStarts).toHaveLength(2);
    expect(toolStarts[0]?.toolName).toBe('search_web');
    expect(toolStarts[1]?.toolName).toBe('execute_code');

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Both tools completed')).toBe(true);
  });

  it('tool calls have unique IDs', async () => {
    await harness.sendMessage('multi-tool');

    const events = harness.getMockAgent().getEventHistory();
    const toolStarts = events.filter((e) => e.type === 'tool_start');

    const ids = toolStarts.map((e) => e.toolCallId);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ids.length);
  });

  it('tool args are properly captured', async () => {
    await harness.sendMessage('chart');

    harness.assertToolCalls([
      {
        name: 'render_chart',
        expectedStatus: 'completed',
        expectedArgs: {
          chartType: 'bar',
          title: 'Test Chart',
        },
      },
    ]);
  });

  it('tool-only response still emits done event', async () => {
    await harness.sendMessage('tool-only');

    const events = harness.getMockAgent().getEventHistory();
    const doneEvents = events.filter((e) => e.type === 'done');
    expect(doneEvents).toHaveLength(1);
  });

  it('text events follow tool events', async () => {
    await harness.sendMessage('chart');

    const events = harness.getMockAgent().getEventHistory();

    // Find last tool_end index
    let lastToolEndIndex = -1;
    events.forEach((e, i) => {
      if (e.type === 'tool_end') lastToolEndIndex = i;
    });

    // Find first text event after tools
    const textAfterTools = events.findIndex(
      (e, i) => e.type === 'text' && i > lastToolEndIndex
    );

    expect(textAfterTools).toBeGreaterThan(lastToolEndIndex);
  });

  it('tool call ID is consistent across lifecycle events', async () => {
    await harness.sendMessage('chart');

    const events = harness.getMockAgent().getEventHistory();

    const startEvent = events.find((e) => e.type === 'tool_start');
    const argsEvent = events.find((e) => e.type === 'tool_args');
    const endEvent = events.find((e) => e.type === 'tool_end');

    expect(startEvent?.toolCallId).toBe(argsEvent?.toolCallId);
    expect(startEvent?.toolCallId).toBe(endEvent?.toolCallId);
  });

  it('multiple tool calls each have complete lifecycle', async () => {
    await harness.sendMessage('multi-tool');

    const events = harness.getMockAgent().getEventHistory();

    // Get all tool call IDs from start events
    const toolStarts = events.filter((e) => e.type === 'tool_start');
    const toolCallIds = toolStarts.map((e) => e.toolCallId);

    // Each ID should have corresponding args and end events
    for (const id of toolCallIds) {
      const hasArgs = events.some(
        (e) => e.type === 'tool_args' && e.toolCallId === id
      );
      const hasEnd = events.some(
        (e) => e.type === 'tool_end' && e.toolCallId === id
      );

      expect(hasArgs).toBe(true);
      expect(hasEnd).toBe(true);
    }
  });
});
