/**
 * Help Screen Component
 *
 * Overlay screen displaying available commands, keyboard shortcuts, and
 * agent descriptions. Closes on Enter or Escape key press.
 */
import { Box, Text, useInput } from 'ink';

interface HelpScreenProps {
  onClose: () => void;
}

export function HelpScreen({ onClose }: HelpScreenProps) {
  useInput((_, key) => {
    if (key.escape || key.return) {
      onClose();
    }
  });

  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="yellow">Solenoid Help</Text>

      <Box marginTop={1} flexDirection="column">
        <Text bold color="cyan">Slash Commands</Text>
        <Box paddingLeft={2} flexDirection="column">
          <Text>/help     - Show this help screen</Text>
          <Text>/settings - View current settings</Text>
          <Text>/clear    - Clear message history</Text>
          <Text>/agents   - List available agents</Text>
          <Text>/quit     - Exit the application</Text>
        </Box>
      </Box>

      <Box marginTop={1} flexDirection="column">
        <Text bold color="cyan">Keyboard Shortcuts</Text>
        <Box paddingLeft={2} flexDirection="column">
          <Text>Ctrl+C    - Quit application</Text>
          <Text>Ctrl+L    - Clear message history</Text>
          <Text>Enter     - Send message</Text>
          <Text>Esc       - Close overlay screens</Text>
        </Box>
      </Box>

      <Box marginTop={1} flexDirection="column">
        <Text bold color="cyan">Available Agents</Text>
        <Box paddingLeft={2} flexDirection="column">
          <Text dimColor>research_agent    - Web search and research</Text>
          <Text dimColor>code_executor     - Run Python code</Text>
          <Text dimColor>chart_generator   - Create Pygal charts</Text>
          <Text dimColor>generic_agent     - General text tasks</Text>
          <Text dimColor>mcp_agent         - External tool integrations</Text>
        </Box>
      </Box>

      <Box marginTop={2}>
        <Text dimColor>Press Enter or Esc to close</Text>
      </Box>
    </Box>
  );
}
