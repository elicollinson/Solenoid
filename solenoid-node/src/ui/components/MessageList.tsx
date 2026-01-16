import { Box, Text } from 'ink';

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

  // Render interleaved parts if available
  const renderParts = () => {
    if (!message.parts || message.parts.length === 0) {
      // Fallback to simple content
      if (!message.content) return null;
      return (
        <Box paddingLeft={2}>
          <Text wrap="wrap">
            {message.content}
            {message.isStreaming && <Text color="gray">▌</Text>}
          </Text>
        </Box>
      );
    }

    return message.parts.map((part, index) => {
      if (part.type === 'text') {
        const isLast = index === message.parts!.length - 1;
        return (
          <Box key={`text-${index}`} paddingLeft={2}>
            <Text wrap="wrap">
              {part.content}
              {isLast && message.isStreaming && <Text color="gray">▌</Text>}
            </Text>
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
