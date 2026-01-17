/**
 * Message List Component
 *
 * Renders the chat conversation history with support for streaming responses,
 * tool call indicators, markdown formatting, and inline chart rendering.
 * Messages display differently based on role (user, assistant, system) with
 * distinct colors and labels.
 *
 * AG-UI Protocol Compliance:
 * - Renders charts inline based on tool call arguments
 * - Charts appear in the message flow where the tool was called
 *
 * Dependencies:
 * - marked: Markdown parser for formatting completed responses
 * - marked-terminal: Terminal-friendly renderer for markdown output
 * - ChartRenderer: Inline chart rendering component
 */
import { Box, Text } from 'ink';
import { useMemo } from 'react';
import { marked } from 'marked';
import TerminalRenderer from 'marked-terminal';
import { ChartRenderer, isChartToolCall } from './ChartRenderer.js';

// Configure marked with terminal renderer
marked.setOptions({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  renderer: new TerminalRenderer({
    reflowText: true,
    width: 80,
  }) as any,
});

function renderMarkdown(content: string): string {
  try {
    const rendered = marked.parse(content);
    // marked.parse can return string or Promise<string>, we only use sync
    if (typeof rendered === 'string') {
      return rendered.trim();
    }
    return content;
  } catch {
    return content;
  }
}

function Markdown({ children }: { children: string }) {
  const rendered = useMemo(() => renderMarkdown(children), [children]);
  return <Text>{rendered}</Text>;
}

export interface ToolCall {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  result?: string;
  /** Tool arguments for AG-UI protocol frontend rendering (e.g., chart data) */
  args?: Record<string, unknown>;
}

export type MessagePart =
  | { type: 'text'; content: string }
  | { type: 'tool_call'; toolCall: ToolCall };

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string; // Keep for backward compat / simple messages
  isStreaming?: boolean;
  parts?: MessagePart[]; // Interleaved content
  agentName?: string;
}

interface MessageListProps {
  messages: Message[];
  maxHeight?: number;
}

function ToolCallDisplay({ toolCall }: { toolCall: ToolCall }) {
  const statusIcons = {
    pending: '○',
    running: '◐',
    completed: '●',
    error: '✗',
  } as const;

  const statusColors = {
    pending: 'gray',
    running: 'yellow',
    completed: 'green',
    error: 'red',
  } as const;

  // Render charts inline when the tool is render_chart and completed
  if (isChartToolCall(toolCall.name) && toolCall.args && toolCall.status === 'completed') {
    return (
      <Box flexDirection="column" paddingLeft={2}>
        <ChartRenderer toolArgs={toolCall.args} />
      </Box>
    );
  }

  // Render chart placeholder while running
  if (isChartToolCall(toolCall.name) && toolCall.status === 'running') {
    return (
      <Box paddingLeft={4} marginY={0}>
        <Text color="yellow">
          {statusIcons[toolCall.status]} Generating chart...
        </Text>
      </Box>
    );
  }

  return (
    <Box paddingLeft={4} marginY={0}>
      <Text color={statusColors[toolCall.status]}>
        {statusIcons[toolCall.status]} {toolCall.name}
      </Text>
      {toolCall.result && toolCall.status === 'error' && (
        <Text color="red" dimColor> - {toolCall.result}</Text>
      )}
    </Box>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const roleColors = {
    user: 'green',
    assistant: 'cyan',
    system: 'yellow',
  } as const;

  const roleLabels = {
    user: 'You',
    assistant: 'Solenoid',
    system: 'System',
  } as const;

  const label = message.agentName || roleLabels[message.role];

  // Render text content - raw while streaming, markdown when complete
  const renderTextContent = (content: string, isStreaming: boolean, showCursor: boolean) => {
    if (isStreaming || !content) {
      // Raw text while streaming to avoid markdown parsing overhead
      return (
        <Text wrap="wrap">
          {content}
          {showCursor && <Text color="gray">▌</Text>}
        </Text>
      );
    }
    // Render as markdown when complete
    return <Markdown>{content}</Markdown>;
  };

  // Render interleaved parts if available
  const renderParts = () => {
    if (!message.parts || message.parts.length === 0) {
      // Fallback to simple content
      if (!message.content) return null;
      return (
        <Box paddingLeft={2}>
          {renderTextContent(message.content, !!message.isStreaming, !!message.isStreaming)}
        </Box>
      );
    }

    return message.parts.map((part, index) => {
      if (part.type === 'text') {
        const isLast = index === message.parts!.length - 1;
        const showCursor = isLast && !!message.isStreaming;
        return (
          <Box key={`text-${index}`} paddingLeft={2}>
            {renderTextContent(part.content, !!message.isStreaming, showCursor)}
          </Box>
        );
      } else {
        return (
          <ToolCallDisplay key={part.toolCall.id} toolCall={part.toolCall} />
        );
      }
    });
  };

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text bold color={roleColors[message.role]}>
        {label}
      </Text>
      {renderParts()}
    </Box>
  );
}

export function MessageList({ messages, maxHeight }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <Box flexDirection="column" paddingY={1}>
        <Text dimColor>No messages yet. Type something to get started!</Text>
      </Box>
    );
  }

  const displayMessages = maxHeight ? messages.slice(-maxHeight) : messages;

  return (
    <Box flexDirection="column" paddingY={1}>
      {displayMessages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
    </Box>
  );
}
