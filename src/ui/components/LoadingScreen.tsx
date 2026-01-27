import { Spinner } from '@inkjs/ui';
import { Box, Text } from 'ink';
/**
 * Loading Screen Component
 *
 * Displayed during agent initialization with a status message.
 */
import { useEffect, useState } from 'react';

interface LoadingScreenProps {
  message?: string;
  error?: Error | null;
}

export function LoadingScreen({ message = 'Initializing agents...', error }: LoadingScreenProps) {
  // Delay spinner animation to avoid Ink rendering race condition
  const [showSpinner, setShowSpinner] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowSpinner(true), 50);
    return () => clearTimeout(timer);
  }, []);

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
      height="100%"
    >
      <Box marginBottom={1}>
        {showSpinner ? <Spinner label={message} /> : <Text>{message}</Text>}
      </Box>
      <Text dimColor>Setting up MCP connections and agent hierarchy...</Text>
    </Box>
  );
}
