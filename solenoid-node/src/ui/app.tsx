import { useState, useCallback } from 'react';
import { Box, useApp, useInput } from 'ink';
import { Header, MessageList, ChatInput, StatusBar, type Message } from './components/index.js';

interface AppProps {
  serverUrl?: string;
}

export function App({ serverUrl = 'http://localhost:8001' }: AppProps) {
  const { exit } = useApp();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState('Ready');

  useInput((char, key) => {
    if (key.ctrl && char === 'c') {
      exit();
    }
    if (key.ctrl && char === 'l') {
      setMessages([]);
    }
  });

  const handleSubmit = useCallback(
    async (text: string) => {
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
      };
      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setStatus('Thinking...');

      const assistantMessageId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        { id: assistantMessageId, role: 'assistant', content: '', isStreaming: true },
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
              } catch {
                // Skip invalid JSON
              }
            }
          }
        }

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId ? { ...msg, isStreaming: false } : msg
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
    [serverUrl]
  );

  return (
    <Box flexDirection="column" height="100%">
      <Header />
      <Box flexDirection="column" flexGrow={1} paddingX={1}>
        <MessageList messages={messages} />
      </Box>
      <ChatInput
        onSubmit={handleSubmit}
        isDisabled={isLoading}
        placeholder={isLoading ? 'Waiting for response...' : 'Ask the agent...'}
      />
      <StatusBar isLoading={isLoading} status={status} serverUrl={serverUrl} />
    </Box>
  );
}
