import { Box, Text } from 'ink';
import { Spinner } from '@inkjs/ui';

interface StatusBarProps {
  isLoading?: boolean;
  status?: string;
  serverUrl?: string;
}

export function StatusBar({
  isLoading = false,
  status = 'Ready',
  serverUrl = 'http://localhost:8001',
}: StatusBarProps) {
  return (
    <Box justifyContent="space-between" paddingX={1}>
      <Box gap={1}>
        {isLoading ? (
          <Spinner label={status} />
        ) : (
          <Text dimColor>{status}</Text>
        )}
      </Box>
      <Box gap={2}>
        <Text dimColor>Server: {serverUrl}</Text>
        <Text dimColor>Ctrl+C to quit</Text>
      </Box>
    </Box>
  );
}
