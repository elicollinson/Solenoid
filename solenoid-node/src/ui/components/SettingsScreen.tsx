/**
 * Settings Screen Component
 *
 * Overlay screen displaying current configuration from app_settings.yaml.
 * Shows model settings, embedding configuration, MCP servers, and
 * per-agent model overrides. Closes on Enter or Escape key press.
 */
import { Box, Text, useInput } from 'ink';
import type { AppSettings } from '../../config/schema.js';

interface SettingsScreenProps {
  settings: AppSettings | null;
  onClose: () => void;
}

export function SettingsScreen({ settings, onClose }: SettingsScreenProps) {
  useInput((_, key) => {
    if (key.escape || key.return) {
      onClose();
    }
  });

  if (!settings) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text bold color="yellow">Settings</Text>
        <Box marginTop={1}>
          <Text color="red">No settings file found. Create app_settings.yaml to configure.</Text>
        </Box>
        <Box marginTop={1}>
          <Text dimColor>Press Enter or Esc to close</Text>
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="yellow">Settings</Text>

      <Box marginTop={1} flexDirection="column">
        <Text bold color="cyan">Models</Text>
        <Box paddingLeft={2} flexDirection="column">
          <Text>Default: {settings.models.default.name}</Text>
          <Text>Provider: {settings.models.default.provider}</Text>
          <Text>Context: {settings.models.default.context_length}</Text>
        </Box>
      </Box>

      <Box marginTop={1} flexDirection="column">
        <Text bold color="cyan">Embeddings</Text>
        <Box paddingLeft={2} flexDirection="column">
          <Text>Provider: {settings.embeddings.provider}</Text>
          <Text>Model: {settings.embeddings.model}</Text>
        </Box>
      </Box>

      <Box marginTop={1} flexDirection="column">
        <Text bold color="cyan">MCP Servers</Text>
        <Box paddingLeft={2} flexDirection="column">
          {Object.keys(settings.mcp_servers).length === 0 ? (
            <Text dimColor>None configured</Text>
          ) : (
            Object.entries(settings.mcp_servers).map(([name, config]) => (
              <Text key={name}>
                {name}: {'command' in config ? `stdio (${config.command})` : `http (${config.url})`}
              </Text>
            ))
          )}
        </Box>
      </Box>

      <Box marginTop={1} flexDirection="column">
        <Text bold color="cyan">Agent Overrides</Text>
        <Box paddingLeft={2} flexDirection="column">
          {!settings.models.agents || Object.keys(settings.models.agents).length === 0 ? (
            <Text dimColor>None configured</Text>
          ) : (
            Object.entries(settings.models.agents).map(([name, config]) => (
              config && <Text key={name}>{name}: {config.name}</Text>
            ))
          )}
        </Box>
      </Box>

      <Box marginTop={2}>
        <Text dimColor>Press Enter or Esc to close</Text>
      </Box>
    </Box>
  );
}
