/**
 * LLM Type Definitions
 *
 * Core interfaces for LLM interactions including messages, tool calls, and
 * provider contracts. Defines the abstraction layer that allows swapping
 * between different LLM backends (Ollama, OpenAI, Anthropic).
 */
import type { Tool as OllamaTool } from 'ollama';

export interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_calls?: ToolCall[];
  tool_name?: string;
}

export interface ToolCall {
  function: {
    name: string;
    arguments: Record<string, unknown>;
  };
}

export interface ToolDefinition {
  type: 'function';
  function: {
    name: string;
    description: string;
    parameters: {
      type: 'object';
      properties: Record<
        string,
        {
          type: string;
          description: string;
          enum?: string[];
        }
      >;
      required?: string[];
    };
  };
}

export interface ChatOptions {
  model: string;
  messages: Message[];
  tools?: ToolDefinition[];
  stream?: boolean;
  systemPrompt?: string;
  temperature?: number;
  maxTokens?: number;
}

export interface ChatResponse {
  message: Message;
  done: boolean;
  done_reason?: 'stop' | 'length' | 'tool_calls';
}

export interface StreamChunk {
  message: {
    role: 'assistant';
    content: string;
    tool_calls?: ToolCall[];
  };
  done: boolean;
  done_reason?: 'stop' | 'length' | 'tool_calls';
}

export type ChatStreamResponse = AsyncGenerator<StreamChunk, void, unknown>;

export interface LLMProvider {
  chat(options: ChatOptions): Promise<ChatResponse>;
  chatStream(options: ChatOptions): ChatStreamResponse;
}

export type { OllamaTool };
