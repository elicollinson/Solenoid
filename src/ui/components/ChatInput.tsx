import { TextInput } from '@inkjs/ui';
import { Box, Text } from 'ink';
/**
 * Chat Input Component
 *
 * Text input field for user messages with visual feedback for disabled state.
 * Clears input after submission by cycling the React key. Styled with a
 * rounded border that changes color based on state.
 *
 * Dependencies:
 * - @inkjs/ui: UI component library for Ink (TextInput)
 */
import { useCallback, useState } from 'react';
import { uiLogger } from '../../utils/logger.js';

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

  const handleChange = useCallback((value: string) => {
    uiLogger.trace({ value, length: value.length }, 'ChatInput onChange');
  }, []);

  const handleSubmit = useCallback(
    (text: string) => {
      uiLogger.debug({ text }, 'ChatInput handleSubmit');
      const trimmed = text.trim();
      if (trimmed) {
        onSubmit(trimmed);
        // Force TextInput to reset by changing its key
        setKey((k) => k + 1);
        uiLogger.debug({ newKey: key + 1 }, 'ChatInput key incremented');
      }
    },
    [onSubmit, key]
  );

  uiLogger.trace({ key, isDisabled, placeholder }, 'ChatInput render');

  return (
    <Box borderStyle="round" borderColor={isDisabled ? 'gray' : 'green'} paddingX={1}>
      <Text color={isDisabled ? 'gray' : 'green'}>{'> '}</Text>
      <TextInput
        key={key}
        placeholder={placeholder}
        onChange={handleChange}
        onSubmit={handleSubmit}
        isDisabled={isDisabled}
      />
    </Box>
  );
}
