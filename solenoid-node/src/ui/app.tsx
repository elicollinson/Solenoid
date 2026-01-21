/**
 * Main App Component
 *
 * Root React component for the terminal UI. Uses React 18 Suspense for
 * agent initialization loading state. Manages chat state, screen navigation,
 * and direct ADK agent invocation.
 *
 * Dependencies:
 * - ink: React-based terminal UI framework
 * - React Suspense: Handles loading state during agent initialization
 */
import { useState, useEffect, Suspense } from "react";
import { Box, useApp, useInput } from "ink";
import {
  Header,
  MessageList,
  ChatInput,
  StatusBar,
  SettingsScreen,
  HelpScreen,
  LoadingScreen,
  ErrorBoundary,
  type Message,
  type MessagePart,
  type ToolCall,
} from "./components/index.js";
import { useAgent } from "./hooks/index.js";
import { loadSettings } from "../config/index.js";
import { uiLogger } from "../utils/logger.js";

type Screen = "chat" | "settings" | "help";

export function App() {
  return (
    <ErrorBoundary fallback={(error) => <LoadingScreen error={error} />}>
      <Suspense fallback={<LoadingScreen message="Initializing agents..." />}>
        <AppContent />
      </Suspense>
    </ErrorBoundary>
  );
}

function AppContent() {
  const { exit } = useApp();
  const agent = useAgent(); // Will suspend until MCP tools are loaded

  const [messages, setMessages] = useState<Message[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [screen, setScreen] = useState<Screen>("chat");

  useEffect(() => {
    uiLogger.debug("App useEffect: loading settings");
    try {
      loadSettings();
      uiLogger.info("Settings loaded successfully");
    } catch (error) {
      uiLogger.warn({ error }, "Settings not available");
    }
  }, []);

  // Escape key handler for non-chat screens
  useInput(
    (_char, key) => {
      if (key.escape) {
        uiLogger.info("Escape pressed, returning to chat");
        setScreen("chat");
      }
    },
    { isActive: screen !== "chat" }
  );

  const handleSlashCommand = (command: string): boolean => {
    const cmd = command.toLowerCase().trim();
    switch (cmd) {
      case "/help":
        setScreen("help");
        return true;
      case "/settings":
        setScreen("settings");
        return true;
      case "/clear":
        setMessages([]);
        return true;
      case "/quit":
      case "/exit":
        exit();
        return true;
      case "/agents":
        const agentList: Message = {
          id: crypto.randomUUID(),
          role: "system",
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
        if (command.startsWith("/")) {
          const unknownCmd: Message = {
            id: crypto.randomUUID(),
            role: "system",
            content: `Unknown command: ${command}. Type /help for available commands.`,
          };
          setMessages((prev) => [...prev, unknownCmd]);
          return true;
        }
        return false;
    }
  };

  const handleSubmit = async (text: string) => {
    uiLogger.info({ text }, "handleSubmit called");

    // Handle slash commands
    if (text.startsWith("/")) {
      uiLogger.debug({ text }, "Processing slash command");
      handleSlashCommand(text);
      return;
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    uiLogger.debug({ messageId: userMessage.id }, "Adding user message");
    setMessages((prev) => [...prev, userMessage]);
    setIsProcessing(true);
    setStatus("Thinking...");

    const assistantMessageId = crypto.randomUUID();
    const parts: MessagePart[] = [];
    const toolCallMap = new Map<string, ToolCall>();

    setMessages((prev) => [
      ...prev,
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        isStreaming: true,
        parts: [],
      },
    ]);

    try {
      // Direct ADK invocation via hook
      for await (const event of agent.run(text)) {
        switch (event.type) {
          case "text":
            if (event.content) {
              // Append to last text part or create new one
              const lastPart = parts[parts.length - 1];
              if (lastPart && lastPart.type === "text") {
                lastPart.content += event.content;
              } else {
                parts.push({ type: "text", content: event.content });
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        content: msg.content + event.content,
                        parts: [...parts],
                      }
                    : msg
                )
              );
            }
            break;

          case "tool_start":
            if (event.toolCallId && event.toolName) {
              const newToolCall: ToolCall = {
                id: event.toolCallId,
                name: event.toolName,
                status: "running",
              };
              toolCallMap.set(event.toolCallId, newToolCall);
              parts.push({ type: "tool_call", toolCall: newToolCall });
              setStatus(`Running: ${event.toolName}`);
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? { ...msg, parts: [...parts] }
                    : msg
                )
              );
            }
            break;

          case "tool_args":
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
                    msg.id === assistantMessageId
                      ? { ...msg, parts: [...parts] }
                      : msg
                  )
                );
              }
            }
            break;

          case "tool_end":
            if (event.toolCallId) {
              const tc = toolCallMap.get(event.toolCallId);
              if (tc) {
                tc.status = "completed";
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? { ...msg, parts: [...parts] }
                      : msg
                  )
                );
              }
            }
            break;

          case "transfer":
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

          case "error":
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? {
                      ...msg,
                      content: `Error: ${event.error}`,
                      isStreaming: false,
                    }
                  : msg
              )
            );
            break;
        }
      }

      // Mark any remaining running tool calls as completed
      for (const tc of toolCallMap.values()) {
        if (tc.status === "running") {
          tc.status = "completed";
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
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId
            ? { ...msg, content: `Error: ${errorMessage}`, isStreaming: false }
            : msg
        )
      );
    } finally {
      setIsProcessing(false);
      setStatus("Ready");
    }
  };

  if (screen === "settings") {
    return <SettingsScreen onClose={() => setScreen("chat")} />;
  } else if (screen === "help") {
    return <HelpScreen onClose={() => setScreen("chat")} />;
  }

  return (
    <Box flexDirection="column" height="100%">
      <Header />
      <Box flexDirection="column" flexGrow={1} paddingX={1}>
        <MessageList messages={messages} />
      </Box>
      <ChatInput
        onSubmit={handleSubmit}
        isDisabled={isProcessing}
        placeholder={
          isProcessing
            ? "Waiting for response..."
            : "Ask the agent... (type /help for commands)"
        }
      />
      <StatusBar isLoading={isProcessing} status={status} />
    </Box>
  );
}
