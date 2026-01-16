import { Box, Text } from 'ink';

export interface ToolCall {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  result?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  isStreaming?: boolean;
  toolCalls?: ToolCall[];
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

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text bold color={roleColors[message.role]}>
        {label}
      </Text>
      {message.toolCalls && message.toolCalls.length > 0 && (
        <Box flexDirection="column" paddingLeft={2}>
          {message.toolCalls.map((tc) => (
            <ToolCallDisplay key={tc.id} toolCall={tc} />
          ))}
        </Box>
      )}
      {message.content && (
        <Box paddingLeft={2}>
          <Text wrap="wrap">
            {message.content}
            {message.isStreaming && <Text color="gray">▌</Text>}
          </Text>
        </Box>
      )}
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
