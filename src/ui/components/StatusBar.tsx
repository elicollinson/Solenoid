import { Spinner } from '@inkjs/ui';
/**
 * Status Bar Component
 *
 * Bottom bar showing current status and exit hint.
 */
import { Box, Text } from 'ink';

interface StatusBarProps {
  isLoading?: boolean;
  status?: string;
}

export function StatusBar({ isLoading = false, status = 'Ready' }: StatusBarProps) {
  return (
    <Box justifyContent="space-between" paddingX={1}>
      <Box gap={1}>{isLoading ? <Spinner label={status} /> : <Text dimColor>{status}</Text>}</Box>
      <Text dimColor>Ctrl+C to quit</Text>
    </Box>
  );
}
