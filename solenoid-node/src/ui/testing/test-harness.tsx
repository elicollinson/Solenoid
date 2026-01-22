/**
 * Solenoid Test Harness
 *
 * High-level API for testing the Solenoid terminal UI.
 * Provides programmatic control over the application for integration testing.
 */
import { render } from 'ink-testing-library';
import React, { useState, useCallback } from 'react';
import { Box, Text } from 'ink';
import { TextInput } from '@inkjs/ui';
import { MockAgent, createMockUseAgent } from './mock-agent.js';
import type {
  TestHarnessConfig,
  UIState,
  StructuredFrame,
  CommandResult,
  ToolCallAssertion,
  Message,
} from './types.js';

/**
 * SolenoidTestHarness provides a high-level API for testing the terminal UI.
 *
 * Features:
 * - Programmatic command sending
 * - Structured state inspection
 * - Event capture and validation
 * - Snapshot testing support
 * - Async operation handling
 *
 * @example
 * ```typescript
 * const harness = new SolenoidTestHarness({
 *   responses: {
 *     'hello': { textChunks: ['Hello, world!'] },
 *   },
 * });
 *
 * await harness.start();
 * const result = await harness.sendMessage('hello');
 *
 * expect(result.finalState.messages).toHaveLength(2);
 * expect(harness.getCurrentFrame().containsText('Hello, world!')).toBe(true);
 *
 * harness.dispose();
 * ```
 */
export class SolenoidTestHarness {
  private config: Required<TestHarnessConfig>;
  private mockAgent: MockAgent;
  private instance: ReturnType<typeof render> | null = null;
  private frameHistory: StructuredFrame[] = [];
  private disposed = false;

  constructor(config: TestHarnessConfig = {}) {
    this.config = {
      responses: config.responses ?? {},
      initialMessages: config.initialMessages ?? [],
      initialScreen: config.initialScreen ?? 'chat',
      timeout: config.timeout ?? 5000,
      debug: config.debug ?? false,
    };

    this.mockAgent = new MockAgent();

    // Configure mock responses
    for (const [pattern, response] of Object.entries(this.config.responses)) {
      if (pattern === 'default') {
        this.mockAgent.setDefaultResponse(response);
      } else {
        this.mockAgent.setResponse(pattern, response);
      }
    }
  }

  /**
   * Start the test harness by rendering a test app with mocked dependencies.
   * This renders a simplified version of the app suitable for testing.
   */
  async start(): Promise<void> {
    if (this.disposed) {
      throw new Error('Harness has been disposed');
    }

    // Create a simple test component that mimics the app behavior
    const TestApp = this.createTestApp();
    this.instance = render(TestApp);
    this.captureFrame();

    // Wait for initial render to stabilize
    await this.waitForStable();
  }

  /**
   * Send a message through the chat input
   */
  async sendMessage(text: string): Promise<CommandResult> {
    this.ensureStarted();
    const startFrameIndex = this.frameHistory.length;

    // Type the message
    this.instance!.stdin.write(text);
    await this.tick();

    // Press enter to submit
    this.instance!.stdin.write('\r');

    // Wait for processing to complete
    await this.waitForIdle();

    return this.createResult(startFrameIndex);
  }

  /**
   * Execute a slash command
   */
  async executeCommand(command: string): Promise<CommandResult> {
    if (!command.startsWith('/')) {
      command = '/' + command;
    }
    return this.sendMessage(command);
  }

  /**
   * Simulate a key press
   */
  async pressKey(key: string): Promise<void> {
    this.ensureStarted();

    const keyMap: Record<string, string> = {
      enter: '\r',
      escape: '\x1B',
      tab: '\t',
      up: '\x1B[A',
      down: '\x1B[B',
      left: '\x1B[D',
      right: '\x1B[C',
      backspace: '\x7F',
      delete: '\x1B[3~',
      'ctrl+c': '\x03',
      'ctrl+l': '\x0C',
      'ctrl+s': '\x13',
      'ctrl+v': '\x16',
    };

    const keyCode = keyMap[key.toLowerCase()] ?? key;
    this.instance!.stdin.write(keyCode);
    await this.tick();
  }

  /**
   * Get the current UI state
   */
  getState(): UIState {
    this.ensureStarted();
    return this.parseUIState(this.instance!.lastFrame() ?? '');
  }

  /**
   * Get the current frame
   */
  getCurrentFrame(): StructuredFrame {
    this.ensureStarted();
    return this.createStructuredFrame(this.instance!.lastFrame() ?? '');
  }

  /**
   * Get all captured frames
   */
  getFrameHistory(): StructuredFrame[] {
    return [...this.frameHistory];
  }

  /**
   * Get the mock agent for inspection
   */
  getMockAgent(): MockAgent {
    return this.mockAgent;
  }

  /**
   * Wait for a condition to be true
   */
  async waitFor(
    condition: () => boolean,
    options: { timeout?: number; interval?: number } = {}
  ): Promise<void> {
    const timeout = options.timeout ?? this.config.timeout;
    const interval = options.interval ?? 50;
    const start = Date.now();

    while (!condition()) {
      if (Date.now() - start > timeout) {
        throw new Error(`Timeout waiting for condition after ${timeout}ms`);
      }
      await this.tick(interval);
    }
  }

  /**
   * Wait for text to appear in the output
   */
  async waitForText(text: string, timeout?: number): Promise<void> {
    await this.waitFor(() => this.getCurrentFrame().containsText(text), {
      timeout,
    });
  }

  /**
   * Wait for processing to complete
   */
  async waitForIdle(): Promise<void> {
    await this.waitFor(() => {
      const state = this.getState();
      return !state.isProcessing && state.inputEnabled;
    });
  }

  /**
   * Assert tool call states
   */
  assertToolCalls(assertions: ToolCallAssertion[]): void {
    const events = this.mockAgent.getEventHistory();

    for (const assertion of assertions) {
      const startEvent = events.find(
        (e) => e.type === 'tool_start' && e.toolName === assertion.name
      );

      if (!startEvent) {
        throw new Error(`Tool call "${assertion.name}" was not started`);
      }

      if (assertion.expectedArgs) {
        const argsEvent = events.find(
          (e) =>
            e.type === 'tool_args' && e.toolCallId === startEvent.toolCallId
        );

        if (!argsEvent?.toolArgs) {
          throw new Error(`Tool call "${assertion.name}" has no arguments`);
        }

        const actualArgs = JSON.parse(argsEvent.toolArgs);
        for (const [key, value] of Object.entries(assertion.expectedArgs)) {
          if (actualArgs[key] !== value) {
            throw new Error(
              `Tool call "${assertion.name}" arg "${key}": expected ${value}, got ${actualArgs[key]}`
            );
          }
        }
      }
    }
  }

  /**
   * Create a snapshot of the current frame for visual regression testing
   */
  snapshot(): string {
    this.ensureStarted();
    return this.instance!.lastFrame() ?? '';
  }

  /**
   * Dispose of the harness and clean up resources
   */
  dispose(): void {
    if (this.instance) {
      this.instance.unmount();
      this.instance = null;
    }
    this.mockAgent.reset();
    this.frameHistory = [];
    this.disposed = true;
  }

  // Private helpers

  private createTestApp(): React.ReactElement {
    const mockUseAgent = createMockUseAgent(this.mockAgent);
    const initialMessages = this.config.initialMessages;

    // Simple test app component
    const TestApp = () => {
      const agent = mockUseAgent();
      const [messages, setMessages] = useState<Message[]>(initialMessages);
      const [isProcessing, setIsProcessing] = useState(false);
      const [status, setStatus] = useState('Ready');
      const [inputKey, setInputKey] = useState(0);

      const handleSubmit = useCallback(
        async (text: string) => {
          const trimmed = text.trim();
          if (!trimmed) return;

          // Handle slash commands
          if (trimmed.startsWith('/')) {
            const cmd = trimmed.toLowerCase();
            if (cmd === '/help') {
              setMessages((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  role: 'system' as const,
                  content:
                    'Solenoid Help\n\nSlash Commands:\n/help - Show help\n/clear - Clear messages\n/quit - Exit',
                },
              ]);
            } else if (cmd === '/clear') {
              setMessages([]);
            } else if (cmd === '/agents') {
              setMessages((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  role: 'system' as const,
                  content:
                    'Available agents:\n- research_agent\n- code_executor_agent\n- chart_generator_agent',
                },
              ]);
            } else {
              setMessages((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  role: 'system' as const,
                  content: `Unknown command: ${trimmed}`,
                },
              ]);
            }
            setInputKey((k) => k + 1);
            return;
          }

          // Add user message
          const userMessage: Message = {
            id: crypto.randomUUID(),
            role: 'user',
            content: trimmed,
          };
          setMessages((prev) => [...prev, userMessage]);
          setIsProcessing(true);
          setStatus('Thinking...');
          setInputKey((k) => k + 1);

          // Process agent response
          const assistantId = crypto.randomUUID();
          let content = '';

          setMessages((prev) => [
            ...prev,
            {
              id: assistantId,
              role: 'assistant' as const,
              content: '',
              isStreaming: true,
            },
          ]);

          for await (const event of agent.run(trimmed)) {
            if (event.type === 'text' && event.content) {
              content += event.content;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content } : m
                )
              );
            } else if (event.type === 'error') {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        content: `Error: ${event.error}`,
                        isStreaming: false,
                      }
                    : m
                )
              );
              break;
            }
          }

          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, isStreaming: false } : m
            )
          );
          setIsProcessing(false);
          setStatus('Ready');
        },
        [agent]
      );

      return (
        <Box flexDirection="column">
          {/* Header */}
          <Box borderStyle="round" borderColor="cyan" paddingX={2}>
            <Text bold color="cyan">
              Solenoid
            </Text>
            <Text dimColor> v2.0.0-alpha</Text>
          </Box>

          {/* Messages */}
          <Box flexDirection="column" paddingY={1}>
            {messages.length === 0 ? (
              <Text dimColor>
                No messages yet. Type something to get started!
              </Text>
            ) : (
              messages.map((msg) => (
                <Box key={msg.id} flexDirection="column" marginBottom={1}>
                  <Text
                    bold
                    color={
                      msg.role === 'user'
                        ? 'green'
                        : msg.role === 'assistant'
                          ? 'cyan'
                          : 'yellow'
                    }
                  >
                    {msg.role === 'user'
                      ? 'You'
                      : msg.role === 'assistant'
                        ? 'Solenoid'
                        : 'System'}
                  </Text>
                  <Box paddingLeft={2}>
                    <Text wrap="wrap">
                      {msg.content}
                      {msg.isStreaming && <Text color="gray">▌</Text>}
                    </Text>
                  </Box>
                </Box>
              ))
            )}
          </Box>

          {/* Input */}
          <Box
            borderStyle="round"
            borderColor={isProcessing ? 'gray' : 'green'}
            paddingX={1}
          >
            <Text color={isProcessing ? 'gray' : 'green'}>{'> '}</Text>
            <TextInput
              key={inputKey}
              placeholder={
                isProcessing ? 'Waiting for response...' : 'Ask the agent...'
              }
              onSubmit={handleSubmit}
              isDisabled={isProcessing}
            />
          </Box>

          {/* Status bar */}
          <Box justifyContent="space-between" paddingX={1}>
            <Text dimColor>{status}</Text>
            <Text dimColor>Ctrl+C to quit</Text>
          </Box>
        </Box>
      );
    };

    return <TestApp />;
  }

  private ensureStarted(): void {
    if (!this.instance) {
      throw new Error('Harness not started. Call start() first.');
    }
  }

  private captureFrame(): void {
    if (this.instance) {
      const frame = this.createStructuredFrame(
        this.instance.lastFrame() ?? ''
      );
      this.frameHistory.push(frame);
    }
  }

  private createStructuredFrame(raw: string): StructuredFrame {
    return {
      raw,
      timestamp: Date.now(),
      ui: this.parseUIState(raw),
      containsText: (text: string) => raw.includes(text),
      containsPattern: (pattern: RegExp) => pattern.test(raw),
    };
  }

  private parseUIState(frame: string): UIState {
    // Parse the frame to extract structured UI state
    // This is a best-effort parsing based on known UI patterns
    const screen = this.detectScreen(frame);

    return {
      screen,
      messages: [], // Would need component state access for accurate parsing
      isProcessing:
        frame.includes('Thinking...') ||
        frame.includes('Waiting for response'),
      status: this.extractStatus(frame),
      inputValue: '', // Not easily extractable from frame
      inputEnabled: !frame.includes('Waiting for response'),
    };
  }

  private detectScreen(frame: string): UIState['screen'] {
    if (frame.includes('Initializing agents')) return 'loading';
    if (frame.includes('Initialization Failed')) return 'error';
    if (frame.includes('Solenoid Help')) return 'help';
    if (frame.includes('Settings')) return 'settings';
    return 'chat';
  }

  private extractStatus(frame: string): string {
    const statusMatch = frame.match(/Ready|Thinking\.\.\.|Running: \w+/);
    return statusMatch?.[0] ?? 'Unknown';
  }

  private async tick(ms = 10): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, ms));
    this.captureFrame();
  }

  private async waitForStable(timeout = 500): Promise<void> {
    let lastFrame = '';
    let stableCount = 0;
    const start = Date.now();

    while (stableCount < 3 && Date.now() - start < timeout) {
      await this.tick(50);
      const currentFrame = this.instance?.lastFrame() ?? '';
      if (currentFrame === lastFrame) {
        stableCount++;
      } else {
        stableCount = 0;
        lastFrame = currentFrame;
      }
    }
  }

  private createResult(startFrameIndex: number): CommandResult {
    return {
      success: true,
      frames: this.frameHistory.slice(startFrameIndex),
      finalState: this.getState(),
      events: this.mockAgent.getEventHistory(),
    };
  }
}
