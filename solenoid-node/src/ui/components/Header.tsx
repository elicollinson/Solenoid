import { Box, Text } from 'ink';

interface HeaderProps {
  title?: string;
  version?: string;
}

export function Header({ title = 'Solenoid', version = '2.0.0-alpha' }: HeaderProps) {
  return (
    <Box
      borderStyle="round"
      borderColor="cyan"
      paddingX={2}
      justifyContent="space-between"
    >
      <Text bold color="cyan">
        {title}
      </Text>
      <Text dimColor>v{version}</Text>
    </Box>
  );
}
