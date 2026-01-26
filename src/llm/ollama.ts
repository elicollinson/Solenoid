/**
 * Ollama LLM Provider
 *
 * LLM provider implementation for Ollama. Handles chat completions with
 * support for streaming, tool calls, and system prompts. Connects to a
 * local Ollama instance (default: localhost:11434).
 *
 * Dependencies:
 * - ollama: Official Ollama JavaScript client for local LLM inference
 */
import { Ollama } from 'ollama';
import type {
  ChatOptions,
  ChatResponse,
  ChatStreamResponse,
  LLMProvider,
  Message,
  StreamChunk,
} from './types.js';

export class OllamaProvider implements LLMProvider {
  private client: Ollama;

  constructor(host: string = 'http://localhost:11434') {
    this.client = new Ollama({ host });
  }

  async chat(options: ChatOptions): Promise<ChatResponse> {
    const messages = this.prepareMessages(options.messages, options.systemPrompt);

    const response = await this.client.chat({
      model: options.model,
      messages: messages.map((m) => ({
        role: m.role as 'user' | 'assistant' | 'system' | 'tool',
        content: m.content,
        tool_calls: m.tool_calls?.map((tc) => ({
          function: {
            name: tc.function.name,
            arguments: tc.function.arguments,
          },
        })),
      })),
      tools: options.tools?.map((t) => ({
        type: 'function' as const,
        function: t.function,
      })),
      stream: false,
      options: {
        temperature: options.temperature,
        num_predict: options.maxTokens,
      },
    });

    return {
      message: {
        role: 'assistant',
        content: response.message.content,
        tool_calls: response.message.tool_calls?.map((tc) => ({
          function: {
            name: tc.function.name,
            arguments: tc.function.arguments as Record<string, unknown>,
          },
        })),
      },
      done: true,
      done_reason: response.message.tool_calls ? 'tool_calls' : 'stop',
    };
  }

  async *chatStream(options: ChatOptions): ChatStreamResponse {
    const messages = this.prepareMessages(options.messages, options.systemPrompt);

    const response = await this.client.chat({
      model: options.model,
      messages: messages.map((m) => ({
        role: m.role as 'user' | 'assistant' | 'system' | 'tool',
        content: m.content,
      })),
      tools: options.tools?.map((t) => ({
        type: 'function' as const,
        function: t.function,
      })),
      stream: true,
      options: {
        temperature: options.temperature,
        num_predict: options.maxTokens,
      },
    });

    for await (const part of response) {
      const chunk: StreamChunk = {
        message: {
          role: 'assistant',
          content: part.message.content,
          tool_calls: part.message.tool_calls?.map((tc) => ({
            function: {
              name: tc.function.name,
              arguments: tc.function.arguments as Record<string, unknown>,
            },
          })),
        },
        done: part.done,
        done_reason: part.done
          ? part.message.tool_calls
            ? 'tool_calls'
            : 'stop'
          : undefined,
      };
      yield chunk;
    }
  }

  private prepareMessages(messages: Message[], systemPrompt?: string): Message[] {
    const result: Message[] = [];

    if (systemPrompt) {
      result.push({ role: 'system', content: systemPrompt });
    }

    for (const msg of messages) {
      if (msg.role === 'system' && systemPrompt) {
        continue;
      }
      result.push(msg);
    }

    return result;
  }

  async listModels(): Promise<string[]> {
    const response = await this.client.list();
    return response.models.map((m) => m.name);
  }

  async embeddings(model: string, text: string): Promise<number[]> {
    const response = await this.client.embed({
      model,
      input: text,
    });
    return response.embeddings[0] ?? [];
  }
}

let defaultProvider: OllamaProvider | null = null;

export function getOllamaProvider(host?: string): OllamaProvider {
  if (!defaultProvider) {
    defaultProvider = new OllamaProvider(host);
  }
  return defaultProvider;
}
