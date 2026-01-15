import { Box, Text } from 'ink';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  isStreaming?: boolean;
}

interface MessageListProps {
  messages: Message[];
  maxHeight?: number;
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

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text bold color={roleColors[message.role]}>
        {roleLabels[message.role]}
      </Text>
      <Box paddingLeft={2}>
        <Text wrap="wrap">
          {message.content}
          {message.isStreaming && <Text color="gray">▌</Text>}
        </Text>
      </Box>
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
