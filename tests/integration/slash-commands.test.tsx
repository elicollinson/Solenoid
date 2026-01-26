/**
 * Slash Commands Integration Tests
 *
 * Tests for slash command handling in the Solenoid terminal UI.
 */
import { describe, it, expect, beforeEach, afterEach } from 'bun:test';
import { SolenoidTestHarness } from '../../src/ui/testing/index.js';

describe('Slash Commands', () => {
  let harness: SolenoidTestHarness;

  beforeEach(async () => {
    harness = new SolenoidTestHarness({
      responses: {
        default: { textChunks: ['Test response'] },
      },
    });
    await harness.start();
  });

  afterEach(() => {
    harness.dispose();
  });

  it('/help displays help content', async () => {
    await harness.executeCommand('/help');

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Solenoid Help')).toBe(true);
    expect(frame.containsText('Slash Commands')).toBe(true);
  });

  it('/clear removes all messages', async () => {
    // First send a message to have something to clear
    await harness.sendMessage('Hello');
    await harness.waitForIdle();

    // Verify message was added
    let frame = harness.getCurrentFrame();
    expect(frame.containsText('Hello')).toBe(true);

    // Clear messages
    await harness.executeCommand('/clear');

    // Verify messages were cleared
    frame = harness.getCurrentFrame();
    expect(frame.containsText('No messages yet')).toBe(true);
  });

  it('/agents lists available agents', async () => {
    await harness.executeCommand('/agents');

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Available agents')).toBe(true);
    expect(frame.containsText('research_agent')).toBe(true);
    expect(frame.containsText('code_executor_agent')).toBe(true);
    expect(frame.containsText('chart_generator_agent')).toBe(true);
  });

  it('unknown command shows error message', async () => {
    await harness.executeCommand('/unknown_command');

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Unknown command')).toBe(true);
    expect(frame.containsText('/unknown_command')).toBe(true);
  });

  it('commands are case-insensitive', async () => {
    await harness.executeCommand('/HELP');

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Solenoid Help')).toBe(true);
  });

  it('commands work with leading slash added automatically', async () => {
    await harness.executeCommand('help'); // Without leading slash

    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Solenoid Help')).toBe(true);
  });

  it('commands preserve message history except /clear', async () => {
    // Send some messages
    await harness.sendMessage('Message 1');
    await harness.waitForIdle();

    await harness.sendMessage('Message 2');
    await harness.waitForIdle();

    // Run /agents which adds a system message
    await harness.executeCommand('/agents');

    // All messages should still be visible
    const frame = harness.getCurrentFrame();
    expect(frame.containsText('Message 1')).toBe(true);
    expect(frame.containsText('Message 2')).toBe(true);
    expect(frame.containsText('Available agents')).toBe(true);
  });
});
