import { useState, useCallback } from 'react';
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
  const [key, setKey] = useState(0);

  const handleSubmit = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (trimmed) {
        onSubmit(trimmed);
        // Force TextInput to reset by changing its key
        setKey((k) => k + 1);
      }
    },
    [onSubmit]
  );

  return (
    <Box borderStyle="round" borderColor={isDisabled ? 'gray' : 'green'} paddingX={1}>
      <Text color={isDisabled ? 'gray' : 'green'}>{'> '}</Text>
      <TextInput
        key={key}
        placeholder={placeholder}
        onSubmit={handleSubmit}
        isDisabled={isDisabled}
      />
    </Box>
  );
}
