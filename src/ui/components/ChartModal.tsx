/**
 * Chart Modal Component
 *
 * Full-screen modal for viewing charts in expanded form.
 * Press ESC to close and return to the chat.
 *
 * This is used when charts need to be viewed in a larger format
 * outside of the inline chat display.
 */
import { Box, Text, useInput } from 'ink';
import { ChartRenderer } from './ChartRenderer.js';

interface ChartModalProps {
  toolArgs: Record<string, unknown>;
  onClose: () => void;
}

export function ChartModal({ toolArgs, onClose }: ChartModalProps) {
  useInput((_, key) => {
    if (key.escape) {
      onClose();
    }
  });

  const title = (toolArgs.title as string) || 'Chart';
  const chartType = (toolArgs.chartType as string) || 'unknown';

  return (
    <Box
      flexDirection="column"
      width="100%"
      height="100%"
      borderStyle="double"
      borderColor="cyan"
      padding={1}
    >
      {/* Header */}
      <Box justifyContent="space-between" marginBottom={1}>
        <Text bold color="cyan">
          {title} ({chartType} chart)
        </Text>
        <Text dimColor>Press ESC to close</Text>
      </Box>

      {/* Chart content - use larger width for modal view */}
      <Box flexDirection="column" flexGrow={1}>
        <ChartRenderer
          toolArgs={{
            ...toolArgs,
            // Use larger width for modal view
            width: toolArgs.width || '80',
          }}
        />
      </Box>

      {/* Footer */}
      <Box marginTop={1}>
        <Text dimColor>Chart type: {chartType} | Press ESC to return to chat</Text>
      </Box>
    </Box>
  );
}
