/**
 * MessageList Component Tests
 *
 * Unit tests for the MessageList component that displays chat messages.
 */
import { describe, it, expect } from 'bun:test';
import { render } from 'ink-testing-library';
import React from 'react';
import { MessageList, type Message } from '../../../../src/ui/components/MessageList.js';

describe('MessageList', () => {
  it('shows empty state when no messages', () => {
    const { lastFrame } = render(<MessageList messages={[]} />);

    expect(lastFrame()).toContain('No messages yet');
    expect(lastFrame()).toContain('Type something to get started');
  });

  it('renders user message with "You" label', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'user',
        content: 'Hello agent',
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('You');
    expect(lastFrame()).toContain('Hello agent');
  });

  it('renders assistant message with "Solenoid" label', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'assistant',
        content: 'Hello human',
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('Solenoid');
    expect(lastFrame()).toContain('Hello human');
  });

  it('renders system message with "System" label', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'system',
        content: 'System notification',
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('System');
    expect(lastFrame()).toContain('System notification');
  });

  it('shows streaming cursor when message is streaming', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'assistant',
        content: 'Thinking',
        isStreaming: true,
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    // Streaming cursor character
    expect(lastFrame()).toContain('▌');
  });

  it('does not show cursor for completed messages', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'assistant',
        content: 'Complete response',
        isStreaming: false,
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('Complete response');
    expect(lastFrame()).not.toContain('▌');
  });

  it('renders multiple messages in order', () => {
    const messages: Message[] = [
      { id: '1', role: 'user', content: 'First message' },
      { id: '2', role: 'assistant', content: 'Second message' },
      { id: '3', role: 'user', content: 'Third message' },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('First message');
    expect(lastFrame()).toContain('Second message');
    expect(lastFrame()).toContain('Third message');
  });

  it('uses custom agent name when provided', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'assistant',
        content: 'Research results',
        agentName: 'research_agent',
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('research_agent');
    expect(lastFrame()).not.toContain('Solenoid');
  });

  it('limits displayed messages when maxHeight is set', () => {
    const messages: Message[] = Array.from({ length: 10 }, (_, i) => ({
      id: String(i),
      role: 'user' as const,
      content: `Message ${i}`,
    }));

    const { lastFrame } = render(<MessageList messages={messages} maxHeight={3} />);

    // Should only show the last 3 messages
    expect(lastFrame()).not.toContain('Message 0');
    expect(lastFrame()).toContain('Message 9');
  });

  it('renders tool call with pending status', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'assistant',
        content: '',
        parts: [
          {
            type: 'tool_call',
            toolCall: {
              id: 'tc-1',
              name: 'search_web',
              status: 'pending',
            },
          },
        ],
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('search_web');
    expect(lastFrame()).toContain('○'); // Pending status icon
  });

  it('renders tool call with running status', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'assistant',
        content: '',
        parts: [
          {
            type: 'tool_call',
            toolCall: {
              id: 'tc-1',
              name: 'execute_code',
              status: 'running',
            },
          },
        ],
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('execute_code');
    expect(lastFrame()).toContain('◐'); // Running status icon
  });

  it('renders tool call with completed status', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'assistant',
        content: '',
        parts: [
          {
            type: 'tool_call',
            toolCall: {
              id: 'tc-1',
              name: 'read_file',
              status: 'completed',
            },
          },
        ],
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('read_file');
    expect(lastFrame()).toContain('●'); // Completed status icon
  });

  it('renders tool call with error status', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'assistant',
        content: '',
        parts: [
          {
            type: 'tool_call',
            toolCall: {
              id: 'tc-1',
              name: 'failed_tool',
              status: 'error',
              result: 'Connection failed',
            },
          },
        ],
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('failed_tool');
    expect(lastFrame()).toContain('✗'); // Error status icon
    expect(lastFrame()).toContain('Connection failed');
  });

  it('renders interleaved text and tool calls', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'assistant',
        content: '',
        parts: [
          { type: 'text', content: 'Let me search for that.' },
          {
            type: 'tool_call',
            toolCall: { id: 'tc-1', name: 'search_web', status: 'completed' },
          },
          { type: 'text', content: 'Here are the results.' },
        ],
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    expect(lastFrame()).toContain('Let me search for that.');
    expect(lastFrame()).toContain('search_web');
    expect(lastFrame()).toContain('Here are the results.');
  });

  it('handles empty content gracefully', () => {
    const messages: Message[] = [
      {
        id: '1',
        role: 'assistant',
        content: '',
      },
    ];

    const { lastFrame } = render(<MessageList messages={messages} />);

    // Should still render the label
    expect(lastFrame()).toContain('Solenoid');
  });
});
