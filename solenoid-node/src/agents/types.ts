import type { Message, ToolDefinition, ToolCall } from '../llm/types.js';

export interface AgentContext {
  sessionId: string;
  state: Record<string, unknown>;
  parentAgent?: string;
}

export interface AgentRequest {
  messages: Message[];
  context: AgentContext;
}

export interface AgentResponse {
  message: Message;
  transfer?: string;
  done: boolean;
}

export type AgentStreamResponse = AsyncGenerator<AgentStreamChunk, void, unknown>;

export interface AgentStreamChunk {
  type: 'text' | 'tool_call' | 'tool_result' | 'transfer' | 'done';
  content?: string;
  toolCall?: ToolCall;
  toolResult?: { name: string; result: string };
  transferTo?: string;
}

export type BeforeModelCallback = (
  request: AgentRequest
) => Promise<AgentRequest | null> | AgentRequest | null;

export type AfterModelCallback = (
  request: AgentRequest,
  response: Message
) => Promise<void> | void;

export interface AgentConfig {
  name: string;
  model: string;
  instruction: string | ((context: AgentContext) => string);
  tools?: ToolDefinition[];
  subAgents?: Agent[];
  beforeModelCallback?: BeforeModelCallback;
  afterModelCallback?: AfterModelCallback;
  disallowTransferToParent?: boolean;
}

export interface Agent {
  readonly name: string;
  readonly config: AgentConfig;
  run(request: AgentRequest): AgentStreamResponse;
}

export interface AgentRunner {
  run(
    input: string,
    sessionId?: string
  ): AsyncGenerator<AgentStreamChunk, void, unknown>;
}
