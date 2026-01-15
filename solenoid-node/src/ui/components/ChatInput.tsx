import { Box, Text } from 'ink';
import { TextInput } from '@inkjs/ui';

interface ChatInputProps {
  onSubmit: (value: string) => void;
  isDisabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSubmit,
  isDisabled = false,
  placeholder = 'Ask the agent...',
}: ChatInputProps) {
  const handleSubmit = (text: string) => {
    const trimmed = text.trim();
    if (trimmed) {
      onSubmit(trimmed);
    }
  };

  return (
    <Box borderStyle="round" borderColor={isDisabled ? 'gray' : 'green'} paddingX={1}>
      <Text color={isDisabled ? 'gray' : 'green'}>{'> '}</Text>
      <TextInput
        placeholder={placeholder}
        onSubmit={handleSubmit}
        isDisabled={isDisabled}
      />
    </Box>
  );
}
