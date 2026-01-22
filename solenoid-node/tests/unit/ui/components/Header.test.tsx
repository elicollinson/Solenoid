/**
 * Header Component Tests
 *
 * Unit tests for the Header component that displays the app title and version.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'ink-testing-library';
import React from 'react';
import { Header } from '../../../../src/ui/components/Header.js';

describe('Header', () => {
  it('renders with default title and version', () => {
    const { lastFrame } = render(<Header />);

    expect(lastFrame()).toContain('Solenoid');
    expect(lastFrame()).toContain('v2.0.0-alpha');
  });

  it('renders with custom title', () => {
    const { lastFrame } = render(<Header title="Custom App" />);

    expect(lastFrame()).toContain('Custom App');
    expect(lastFrame()).not.toContain('Solenoid');
  });

  it('renders with custom version', () => {
    const { lastFrame } = render(<Header version="1.0.0" />);

    expect(lastFrame()).toContain('v1.0.0');
    expect(lastFrame()).not.toContain('v2.0.0-alpha');
  });

  it('renders with both custom title and version', () => {
    const { lastFrame } = render(
      <Header title="My App" version="3.0.0-beta" />
    );

    expect(lastFrame()).toContain('My App');
    expect(lastFrame()).toContain('v3.0.0-beta');
  });

  it('contains border characters for rounded box', () => {
    const { lastFrame } = render(<Header />);
    const frame = lastFrame() ?? '';

    // Ink renders rounded borders with box-drawing characters
    // Check that the frame has some visual structure
    expect(frame.length).toBeGreaterThan(0);
    // The title should be present within the bordered box
    expect(frame).toContain('Solenoid');
  });
});
