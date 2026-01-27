/**
 * LoadingScreen Component Tests
 *
 * Unit tests for the LoadingScreen component displayed during initialization.
 */
import { describe, it, expect, beforeEach, afterEach } from 'bun:test';
import { render } from 'ink-testing-library';
import React from 'react';
import { LoadingScreen } from '../../../../src/ui/components/LoadingScreen.js';

describe('LoadingScreen', () => {
  it('renders with default message', () => {
    const { lastFrame } = render(<LoadingScreen />);

    expect(lastFrame()).toContain('Initializing agents...');
  });

  it('renders with custom message', () => {
    const { lastFrame } = render(<LoadingScreen message="Loading MCP tools..." />);

    expect(lastFrame()).toContain('Loading MCP tools...');
    expect(lastFrame()).not.toContain('Initializing agents...');
  });

  it('shows MCP setup info message', () => {
    const { lastFrame } = render(<LoadingScreen />);

    expect(lastFrame()).toContain('Setting up MCP connections');
  });

  it('shows error state when error is provided', () => {
    const error = new Error('Failed to connect to LLM');
    const { lastFrame } = render(<LoadingScreen error={error} />);

    expect(lastFrame()).toContain('Initialization Failed');
    expect(lastFrame()).toContain('Failed to connect to LLM');
  });

  it('shows exit hint in error state', () => {
    const error = new Error('Connection timeout');
    const { lastFrame } = render(<LoadingScreen error={error} />);

    expect(lastFrame()).toContain('Ctrl+C to exit');
  });

  it('does not show normal loading content when error is present', () => {
    const error = new Error('Some error');
    const { lastFrame } = render(<LoadingScreen error={error} message="Loading..." />);

    // Should show error state, not loading state
    expect(lastFrame()).toContain('Initialization Failed');
    expect(lastFrame()).not.toContain('Setting up MCP connections');
  });

  it('handles null error as no error', () => {
    const { lastFrame } = render(<LoadingScreen error={null} />);

    expect(lastFrame()).toContain('Initializing agents...');
    expect(lastFrame()).not.toContain('Initialization Failed');
  });

  it('shows spinner with message', async () => {
    const { lastFrame } = render(<LoadingScreen />);

    // Initially shows message
    expect(lastFrame()).toContain('Initializing agents...');

    // Wait a bit for any async updates
    await Bun.sleep(60);

    // Should still contain the message (spinner label)
    expect(lastFrame()).toContain('Initializing agents...');
  });
});
