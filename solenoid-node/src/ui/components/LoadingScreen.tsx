/**
 * Loading Screen Component
 *
 * Displayed during agent initialization with a spinner and status message.
 */
import { Box, Text } from 'ink';
import { Spinner } from '@inkjs/ui';

interface LoadingScreenProps {
  message?: string;
  error?: Error | null;
}

export function LoadingScreen({
  message = 'Initializing agents...',
  error,
}: LoadingScreenProps) {
  if (error) {
    return (
      <Box flexDirection="column" padding={2}>
        <Text color="red" bold>
          Initialization Failed
        </Text>
        <Text color="red">{error.message}</Text>
        <Text dimColor>Press Ctrl+C to exit</Text>
      </Box>
    );
  }

  return (
    <Box
      flexDirection="column"
      alignItems="center"
      justifyContent="center"
      padding={2}
    >
      <Box marginBottom={1}>
        <Spinner label={message} />
      </Box>
      <Text dimColor>Setting up MCP connections and agent hierarchy...</Text>
    </Box>
  );
}
