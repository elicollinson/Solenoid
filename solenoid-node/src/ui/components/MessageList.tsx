import { Box, Text } from 'ink';
import type { FC } from 'react';
// eslint-disable-next-line @typescript-eslint/no-require-imports
const MarkdownRaw = require('ink-markdown');

// Type assertion for ink-markdown which has incomplete types
const Markdown: FC<{ children: string }> = MarkdownRaw.default || MarkdownRaw;

export interface ToolCall {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  result?: string;
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
    if (isStreaming) {
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
