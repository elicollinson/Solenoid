import { useState, useCallback, useEffect } from 'react';
import { Box, useApp, useInput } from 'ink';
import {
  Header,
  MessageList,
  ChatInput,
  StatusBar,
  SettingsScreen,
  HelpScreen,
  type Message,
  type ToolCall,
} from './components/index.js';
import { loadSettings, type AppSettings } from '../config/index.js';

type Screen = 'chat' | 'settings' | 'help';

interface AppProps {
  serverUrl?: string;
}

export function App({ serverUrl = 'http://localhost:8001' }: AppProps) {
  const { exit } = useApp();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState('Ready');
  const [screen, setScreen] = useState<Screen>('chat');
  const [settings, setSettings] = useState<AppSettings | null>(null);

  useEffect(() => {
    try {
      const loaded = loadSettings();
      setSettings(loaded);
    } catch {
      // Settings not available
    }
  }, []);

  useInput((char, key) => {
    if (screen !== 'chat') {
      if (key.escape) {
        setScreen('chat');
      }
      return;
    }
    if (key.ctrl && char === 'c') {
      exit();
    }
    if (key.ctrl && char === 'l') {
      setMessages([]);
    }
  });

  const handleSlashCommand = useCallback(
    (command: string): boolean => {
      const cmd = command.toLowerCase().trim();
      switch (cmd) {
        case '/help':
          setScreen('help');
          return true;
        case '/settings':
          setScreen('settings');
          return true;
        case '/clear':
          setMessages([]);
          return true;
        case '/quit':
        case '/exit':
          exit();
          return true;
        case '/agents':
          const agentList: Message = {
            id: crypto.randomUUID(),
            role: 'system',
            content: `Available agents:
  - research_agent: Web search and research tasks
  - code_executor_agent: Execute Python code
  - chart_generator_agent: Create Pygal charts
  - generic_agent: General text tasks
  - mcp_agent: External tool integrations`,
          };
          setMessages((prev) => [...prev, agentList]);
          return true;
        default:
          if (command.startsWith('/')) {
            const unknownCmd: Message = {
              id: crypto.randomUUID(),
              role: 'system',
              content: `Unknown command: ${command}. Type /help for available commands.`,
            };
            setMessages((prev) => [...prev, unknownCmd]);
            return true;
          }
          return false;
      }
    },
    [exit]
  );

  const handleSubmit = useCallback(
    async (text: string) => {
      // Handle slash commands
      if (text.startsWith('/')) {
        handleSlashCommand(text);
        return;
      }

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
      };
      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setStatus('Thinking...');

      const assistantMessageId = crypto.randomUUID();
      const toolCalls: ToolCall[] = [];

      setMessages((prev) => [
        ...prev,
        { id: assistantMessageId, role: 'assistant', content: '', isStreaming: true, toolCalls: [] },
      ]);

      try {
        const response = await fetch(`${serverUrl}/api/agent`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages: [{ role: 'user', content: text }],
          }),
        });

        if (!response.ok) {
          throw new Error(`Server error: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No response body');
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));

                if (data.type === 'TEXT_MESSAGE_CONTENT' && data.delta) {
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMessageId
                        ? { ...msg, content: msg.content + data.delta }
                        : msg
                    )
                  );
                }

                if (data.type === 'TOOL_CALL_START' && data.tool_name) {
                  const newToolCall: ToolCall = {
                    id: data.tool_call_id || crypto.randomUUID(),
                    name: data.tool_name,
                    status: 'running',
                  };
                  toolCalls.push(newToolCall);
                  setStatus(`Running: ${data.tool_name}`);
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMessageId
                        ? { ...msg, toolCalls: [...toolCalls] }
                        : msg
                    )
                  );
                }

                if (data.type === 'TOOL_CALL_END' && data.tool_call_id) {
                  const tc = toolCalls.find((t) => t.id === data.tool_call_id);
                  if (tc) {
                    tc.status = data.error ? 'error' : 'completed';
                    tc.result = data.error;
                    setMessages((prev) =>
                      prev.map((msg) =>
                        msg.id === assistantMessageId
                          ? { ...msg, toolCalls: [...toolCalls] }
                          : msg
                      )
                    );
                  }
                }

                if (data.type === 'AGENT_TRANSFER' && data.to_agent) {
                  setStatus(`Agent: ${data.to_agent}`);
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMessageId
                        ? { ...msg, agentName: data.to_agent }
                        : msg
                    )
                  );
                }
              } catch {
                // Skip invalid JSON
              }
            }
          }
        }

        // Mark any remaining running tool calls as completed
        for (const tc of toolCalls) {
          if (tc.status === 'running') {
            tc.status = 'completed';
          }
        }

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? { ...msg, isStreaming: false, toolCalls: [...toolCalls] }
              : msg
          )
        );
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? { ...msg, content: `Error: ${errorMessage}`, isStreaming: false }
              : msg
          )
        );
      } finally {
        setIsLoading(false);
        setStatus('Ready');
      }
    },
    [serverUrl, handleSlashCommand]
  );

  if (screen === 'settings') {
    return <SettingsScreen settings={settings} onClose={() => setScreen('chat')} />;
  }

  if (screen === 'help') {
    return <HelpScreen onClose={() => setScreen('chat')} />;
  }

  return (
    <Box flexDirection="column" height="100%">
      <Header />
      <Box flexDirection="column" flexGrow={1} paddingX={1}>
        <MessageList messages={messages} />
      </Box>
      <ChatInput
        onSubmit={handleSubmit}
        isDisabled={isLoading}
        placeholder={isLoading ? 'Waiting for response...' : 'Ask the agent... (type /help for commands)'}
      />
      <StatusBar isLoading={isLoading} status={status} serverUrl={serverUrl} />
    </Box>
  );
}
