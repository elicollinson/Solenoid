/**
 * StatusBar Component Tests
 *
 * Unit tests for the StatusBar component that shows status and exit hint.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'ink-testing-library';
import React from 'react';
import { StatusBar } from '../../../../src/ui/components/StatusBar.js';

describe('StatusBar', () => {
  it('renders with default status "Ready"', () => {
    const { lastFrame } = render(<StatusBar />);

    expect(lastFrame()).toContain('Ready');
  });

  it('renders with custom status', () => {
    const { lastFrame } = render(<StatusBar status="Processing..." />);

    expect(lastFrame()).toContain('Processing...');
    expect(lastFrame()).not.toContain('Ready');
  });

  it('always shows exit hint', () => {
    const { lastFrame } = render(<StatusBar />);

    expect(lastFrame()).toContain('Ctrl+C to quit');
  });

  it('shows exit hint even when loading', () => {
    const { lastFrame } = render(<StatusBar isLoading={true} status="Loading" />);

    expect(lastFrame()).toContain('Ctrl+C to quit');
  });

  it('renders loading state with spinner label', () => {
    const { lastFrame } = render(
      <StatusBar isLoading={true} status="Thinking..." />
    );

    // When loading, the status is shown as a spinner label
    expect(lastFrame()).toContain('Thinking...');
  });

  it('renders non-loading state without spinner', () => {
    const { lastFrame } = render(
      <StatusBar isLoading={false} status="Ready" />
    );

    expect(lastFrame()).toContain('Ready');
    expect(lastFrame()).toContain('Ctrl+C to quit');
  });

  it('handles empty status gracefully', () => {
    const { lastFrame } = render(<StatusBar status="" />);

    // Should still render the exit hint
    expect(lastFrame()).toContain('Ctrl+C to quit');
  });
});
