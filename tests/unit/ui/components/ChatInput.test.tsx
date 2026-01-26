/**
 * ChatInput Component Tests
 *
 * Unit tests for the ChatInput component that handles user text input.
 *
 * Note: Some interactive tests are skipped because @inkjs/ui's TextInput
 * component doesn't fully support stdin.write() in ink-testing-library.
 * Use the SolenoidTestHarness for integration tests of input behavior.
 */
import { describe, it, expect, mock } from 'bun:test';
import { render } from 'ink-testing-library';
import React from 'react';
import { ChatInput } from '../../../../src/ui/components/ChatInput.js';

describe('ChatInput', () => {
  it('renders with default placeholder', () => {
    const { lastFrame } = render(<ChatInput onSubmit={() => {}} />);

    expect(lastFrame()).toContain('Ask the agent...');
  });

  it('renders with custom placeholder', () => {
    const { lastFrame } = render(
      <ChatInput onSubmit={() => {}} placeholder="Type your message..." />
    );

    expect(lastFrame()).toContain('Type your message...');
    expect(lastFrame()).not.toContain('Ask the agent...');
  });

  it('renders prompt character', () => {
    const { lastFrame } = render(<ChatInput onSubmit={() => {}} />);

    expect(lastFrame()).toContain('>');
  });

  // Note: @inkjs/ui TextInput doesn't propagate stdin.write to onSubmit in tests
  // These behaviors are tested through the SolenoidTestHarness integration tests
  it.skip('calls onSubmit with text when Enter is pressed', async () => {
    const onSubmit = mock(() => {});
    const { stdin } = render(<ChatInput onSubmit={onSubmit} />);

    stdin.write('Hello world');
    await new Promise((r) => setTimeout(r, 50));
    stdin.write('\r');
    await new Promise((r) => setTimeout(r, 50));

    expect(onSubmit).toHaveBeenCalledWith('Hello world');
  });

  it.skip('trims whitespace before submitting', async () => {
    const onSubmit = mock(() => {});
    const { stdin } = render(<ChatInput onSubmit={onSubmit} />);

    stdin.write('  Hello world  ');
    await new Promise((r) => setTimeout(r, 50));
    stdin.write('\r');
    await new Promise((r) => setTimeout(r, 50));

    expect(onSubmit).toHaveBeenCalledWith('Hello world');
  });

  it('does not call onSubmit for empty input', async () => {
    const onSubmit = mock(() => {});
    const { stdin } = render(<ChatInput onSubmit={onSubmit} />);

    // Press Enter without typing - empty submit shouldn't trigger callback
    stdin.write('\r');
    await new Promise((r) => setTimeout(r, 50));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('does not call onSubmit for whitespace-only input', async () => {
    const onSubmit = mock(() => {});
    const { stdin } = render(<ChatInput onSubmit={onSubmit} />);

    stdin.write('   ');
    await new Promise((r) => setTimeout(r, 50));
    stdin.write('\r');
    await new Promise((r) => setTimeout(r, 50));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('renders disabled state with gray border indication', () => {
    const { lastFrame } = render(
      <ChatInput onSubmit={() => {}} isDisabled={true} />
    );

    // When disabled, prompt should still be visible
    expect(lastFrame()).toContain('>');
  });

  it('does not submit when disabled', async () => {
    const onSubmit = mock(() => {});
    const { stdin } = render(
      <ChatInput onSubmit={onSubmit} isDisabled={true} />
    );

    stdin.write('Test message');
    await new Promise((r) => setTimeout(r, 50));
    stdin.write('\r');
    await new Promise((r) => setTimeout(r, 50));

    // Disabled input should not trigger submit
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it.skip('clears input after submission', async () => {
    const onSubmit = mock(() => {});
    const { stdin, lastFrame } = render(<ChatInput onSubmit={onSubmit} />);

    stdin.write('Test message');
    await new Promise((r) => setTimeout(r, 50));
    stdin.write('\r');
    await new Promise((r) => setTimeout(r, 50));

    // After submission, should show placeholder again
    expect(lastFrame()).toContain('Ask the agent...');
  });

  it.skip('handles multiple submissions correctly', async () => {
    const onSubmit = mock(() => {});
    const { stdin } = render(<ChatInput onSubmit={onSubmit} />);

    stdin.write('First message');
    await new Promise((r) => setTimeout(r, 50));
    stdin.write('\r');
    await new Promise((r) => setTimeout(r, 50));

    stdin.write('Second message');
    await new Promise((r) => setTimeout(r, 50));
    stdin.write('\r');
    await new Promise((r) => setTimeout(r, 50));

    expect(onSubmit).toHaveBeenCalledTimes(2);
  });
});
