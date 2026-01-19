/**
 * Main App Component
 *
 * Root React component for the terminal UI. Manages chat state, screen navigation,
 * and direct ADK agent invocation. Handles slash commands (/help, /settings,
 * /clear, /agents, /quit) and keyboard shortcuts (Ctrl+C to quit).
 *
 * Dependencies:
 * - ink: React-based terminal UI framework
 *   - Box: Flexbox layout container
 *   - useApp: Application lifecycle hooks
 *   - useInput: Keyboard input handling
 */
import { useState, useCallback, useEffect } from 'react';
import { Box, useApp, useInput } from 'ink';
import {
  Header,
  MessageList,
  ChatInput,
  StatusBar,
  SettingsScreen,
  HelpScreen,
  LoadingScreen,
  type Message,
  type MessagePart,
  type ToolCall,
} from './components/index.js';
import { useAgent } from './hooks/index.js';
import { loadSettings } from '../config/index.js';
import { uiLogger } from '../utils/logger.js';

type Screen = 'chat' | 'settings' | 'help';

export function App() {
  const { exit } = useApp();
  const agent = useAgent({
    onInitError: (error) => uiLogger.error({ error }, 'Agent initialization failed'),
  });

  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState('Ready');
  const [screen, setScreen] = useState<Screen>('chat');

  useEffect(() => {
    uiLogger.debug('App useEffect: loading settings');
    try {
      loadSettings();
      uiLogger.info('Settings loaded successfully');
    } catch (error) {
      uiLogger.warn({ error }, 'Settings not available');
    }
  }, []);

  // Handle keyboard shortcuts only when not typing in the chat input
  // When on chat screen and not loading, TextInput handles all input
  const inputActive = screen !== 'chat' || isLoading;

  useInput(
    (char, key) => {
      uiLogger.debug({ char, key, screen, inputActive }, 'useInput received');
      if (screen !== 'chat') {
        if (key.escape) {
          uiLogger.info('Escape pressed, returning to chat');
          setScreen('chat');
        }
        return;
      }
      // These work when loading (user might want to see they can quit)
      if (key.ctrl && char === 'c') {
        uiLogger.info('Ctrl+C pressed, exiting');
        exit();
      }
    },
    { isActive: inputActive }
  );

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
      uiLogger.info({ text }, 'handleSubmit called');

      // Handle slash commands
      if (text.startsWith('/')) {
        uiLogger.debug({ text }, 'Processing slash command');
        handleSlashCommand(text);
        return;
      }

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
      };
      uiLogger.debug({ messageId: userMessage.id }, 'Adding user message');
      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setStatus('Thinking...');

      const assistantMessageId = crypto.randomUUID();
      const parts: MessagePart[] = [];
      const toolCallMap = new Map<string, ToolCall>();

      setMessages((prev) => [
        ...prev,
        { id: assistantMessageId, role: 'assistant', content: '', isStreaming: true, parts: [] },
      ]);

      try {
        // Direct ADK invocation via hook
        for await (const event of agent.run(text)) {
          switch (event.type) {
            case 'text':
              if (event.content) {
                // Append to last text part or create new one
                const lastPart = parts[parts.length - 1];
                if (lastPart && lastPart.type === 'text') {
                  lastPart.content += event.content;
                } else {
                  parts.push({ type: 'text', content: event.content });
                }
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? { ...msg, content: msg.content + event.content, parts: [...parts] }
                      : msg
                  )
                );
              }
              break;

            case 'tool_start':
              if (event.toolCallId && event.toolName) {
                const newToolCall: ToolCall = {
                  id: event.toolCallId,
                  name: event.toolName,
                  status: 'running',
                };
                toolCallMap.set(event.toolCallId, newToolCall);
                parts.push({ type: 'tool_call', toolCall: newToolCall });
                setStatus(`Running: ${event.toolName}`);
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId ? { ...msg, parts: [...parts] } : msg
                  )
                );
              }
              break;

            case 'tool_args':
              if (event.toolCallId && event.toolArgs) {
                const tc = toolCallMap.get(event.toolCallId);
                if (tc) {
                  try {
                    tc.args = JSON.parse(event.toolArgs);
                  } catch {
                    tc.args = { raw: event.toolArgs };
                  }
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMessageId ? { ...msg, parts: [...parts] } : msg
                    )
                  );
                }
              }
              break;

            case 'tool_end':
              if (event.toolCallId) {
                const tc = toolCallMap.get(event.toolCallId);
                if (tc) {
                  tc.status = 'completed';
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMessageId ? { ...msg, parts: [...parts] } : msg
                    )
                  );
                }
              }
              break;

            case 'transfer':
              if (event.transferTo) {
                setStatus(`Agent: ${event.transferTo}`);
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? { ...msg, agentName: event.transferTo }
                      : msg
                  )
                );
              }
              break;

            case 'error':
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? { ...msg, content: `Error: ${event.error}`, isStreaming: false }
                    : msg
                )
              );
              break;
          }
        }

        // Mark any remaining running tool calls as completed
        for (const tc of toolCallMap.values()) {
          if (tc.status === 'running') {
            tc.status = 'completed';
          }
        }

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? { ...msg, isStreaming: false, parts: [...parts] }
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
    [agent, handleSlashCommand]
  );

  // Show loading screen during initialization
  if (agent.isInitializing) {
    return <LoadingScreen message="Initializing agents..." />;
  }

  if (agent.initError) {
    return <LoadingScreen error={agent.initError} />;
  }

  if (screen === 'settings') {
    return <SettingsScreen onClose={() => setScreen('chat')} />;
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
      <StatusBar isLoading={isLoading} status={status} />
    </Box>
  );
}
