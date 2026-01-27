/**
 * Ollama ADK Integration
 *
 * Provides an Ollama LLM wrapper that integrates with Google ADK's BaseLlm
 * interface, allowing local Ollama models to be used with the ADK agent
 * framework. Uses the native Ollama API for full feature support including
 * tool calling.
 *
 * Model Naming Convention:
 * - Models are prefixed with 'ollama/' (e.g., 'ollama/llama3.2')
 * - The prefix is stripped when calling the actual Ollama API
 *
 * Dependencies:
 * - @google/adk: BaseLlm, LLMRegistry for ADK integration
 * - @google/genai: Content, Part types for message format
 * - ollama: Native Ollama client for local LLM inference
 */
import { BaseLlm, LLMRegistry } from '@google/adk';
import type { BaseLlmConnection, LlmRequest, LlmResponse } from '@google/adk';
import type { BaseTool } from '@google/adk';
import type { Content, FunctionCall, FunctionResponse, Part } from '@google/genai';
import { Ollama } from 'ollama';
import type {
  ChatResponse as OllamaChatResponse,
  Message as OllamaMessage,
  Tool as OllamaTool,
  ToolCall as OllamaToolCall,
} from 'ollama';
import { getOllamaHost } from '../config/settings.js';
import { agentLogger } from '../utils/logger.js';

/**
 * Ollama LLM implementation for Google ADK.
 *
 * Extends BaseLlm to provide Ollama model support within the ADK framework.
 * Supports both streaming and non-streaming generation, as well as tool calls.
 */
export class OllamaLlm extends BaseLlm {
  /**
   * Pattern matching for model names that this LLM handles.
   * Matches any model name starting with 'ollama/'.
   */
  static readonly supportedModels: Array<string | RegExp> = [/^ollama\/.*/];

  private client: Ollama;
  private actualModel: string;

  /**
   * Creates an OllamaLlm instance.
   *
   * @param params.model - The model name with 'ollama/' prefix (e.g., 'ollama/llama3.2')
   */
  constructor({ model }: { model: string }) {
    // Store the full model name for ADK
    super({ model });

    // Strip 'ollama/' prefix for actual Ollama API calls
    this.actualModel = model.replace(/^ollama\//, '');

    // Initialize Ollama client with host from config or env
    const host = getOllamaHost();
    this.client = new Ollama({ host });
  }

  /**
   * Generates content asynchronously from the Ollama model.
   *
   * Converts ADK LlmRequest format to Ollama format, sends the request,
   * and converts the response back to ADK LlmResponse format.
   *
   * @param llmRequest - The ADK request containing contents and tools
   * @param stream - Whether to use streaming mode (default: false)
   * @yields LlmResponse objects containing the model's response
   */
  async *generateContentAsync(
    llmRequest: LlmRequest,
    stream = false
  ): AsyncGenerator<LlmResponse, void> {
    try {
      // Convert ADK Content[] to Ollama Message[]
      const messages = this.convertContents(llmRequest.contents);

      // Convert ADK tools to Ollama format
      const tools = this.convertTools(llmRequest.toolsDict);

      // Extract system instruction from config
      const systemInstruction = llmRequest.config?.systemInstruction;
      if (systemInstruction) {
        const systemContent = this.extractTextFromContent(systemInstruction);
        if (systemContent) {
          messages.unshift({ role: 'system', content: systemContent });
        }
      }

      agentLogger.debug(
        `[OllamaLlm] Calling model: ${this.actualModel}, messages: ${messages.length}, tools: ${tools.length}, stream: ${stream}`
      );
      agentLogger.debug(
        `[OllamaLlm] Available tools: ${tools.map((t) => t.function.name).join(', ') || 'none'}`
      );

      if (stream) {
        // Streaming mode
        const response = await this.client.chat({
          model: this.actualModel,
          messages,
          tools: tools.length > 0 ? tools : undefined,
          stream: true,
        });

        for await (const chunk of response) {
          yield this.convertToLlmResponse(chunk, !chunk.done);
        }
      } else {
        // Non-streaming mode
        const response = await this.client.chat({
          model: this.actualModel,
          messages,
          tools: tools.length > 0 ? tools : undefined,
          stream: false,
        });

        const toolCallCount = response.message.tool_calls?.length ?? 0;
        agentLogger.debug(
          `[OllamaLlm] Response received, done: ${response.done}, content length: ${response.message.content?.length ?? 0}, tool_calls: ${toolCallCount}`
        );
        if (response.message.tool_calls && response.message.tool_calls.length > 0) {
          for (const tc of response.message.tool_calls) {
            agentLogger.debug(`[OllamaLlm] Tool call from Ollama: ${tc.function.name}`);
            agentLogger.debug(`[OllamaLlm] Tool call args type: ${typeof tc.function.arguments}`);
            agentLogger.debug(
              `[OllamaLlm] Tool call args keys: ${Object.keys(tc.function.arguments || {}).join(', ')}`
            );
            agentLogger.debug(
              `[OllamaLlm] Tool call args full: ${JSON.stringify(tc.function.arguments)}`
            );
          }
        }
        const llmResponse = this.convertToLlmResponse(response, false);
        agentLogger.debug(
          `[OllamaLlm] Yielding response with ${llmResponse.content?.parts?.length} parts, turnComplete: ${llmResponse.turnComplete}`
        );
        // Log the parts in the response
        if (llmResponse.content?.parts) {
          for (const part of llmResponse.content.parts) {
            if ('text' in part && part.text) {
              agentLogger.debug(`[OllamaLlm] Part: text (${part.text.length} chars)`);
            }
            if ('functionCall' in part && part.functionCall) {
              agentLogger.debug(
                `[OllamaLlm] Part: functionCall: ${part.functionCall.name}, args: ${JSON.stringify(part.functionCall.args)}`
              );
            }
          }
        }
        yield llmResponse;
      }
    } catch (error) {
      agentLogger.error({ error }, '[OllamaLlm] Error calling Ollama');
      // Yield an error response so ADK can handle it
      yield {
        content: {
          role: 'model',
          parts: [
            {
              text: `Error calling Ollama: ${error instanceof Error ? error.message : String(error)}`,
            },
          ],
        },
        errorCode: 'OLLAMA_ERROR',
        errorMessage: error instanceof Error ? error.message : String(error),
        turnComplete: true,
      };
    }
  }

  /**
   * Creates a live connection to the LLM.
   *
   * Ollama does not support live/realtime bidirectional connections,
   * so this method throws an error.
   *
   * @throws Error indicating Ollama doesn't support live connections
   */
  async connect(_llmRequest: LlmRequest): Promise<BaseLlmConnection> {
    throw new Error('Ollama does not support live/realtime connections');
  }

  /**
   * Converts ADK Content[] to Ollama Message[].
   *
   * Maps between the Gemini/ADK content format and Ollama's message format:
   * - role 'user' → 'user'
   * - role 'model' → 'assistant'
   * - role 'function' → 'tool'
   *
   * @param contents - Array of ADK Content objects
   * @returns Array of Ollama Message objects
   */
  private convertContents(contents: Content[]): OllamaMessage[] {
    const messages: OllamaMessage[] = [];

    for (const content of contents) {
      const role = this.mapRole(content.role);

      // Handle function response content (tool results)
      if (content.role === 'function' || this.hasFunctionResponse(content)) {
        const functionResponses = this.extractFunctionResponses(content);
        for (const fr of functionResponses) {
          messages.push({
            role: 'tool',
            content: JSON.stringify(fr.response),
            tool_name: fr.name,
          });
        }
        continue;
      }

      // Handle model responses with tool calls
      if ((content.role === 'model' || role === 'assistant') && this.hasFunctionCalls(content)) {
        const textContent = this.extractText(content);
        const toolCalls = this.extractToolCalls(content);

        messages.push({
          role: 'assistant',
          content: textContent,
          tool_calls: toolCalls,
        });
        continue;
      }

      // Handle regular text content
      const textContent = this.extractText(content);
      if (textContent || role === 'user') {
        messages.push({
          role,
          content: textContent,
        });
      }
    }

    return messages;
  }

  /**
   * Maps ADK/Gemini roles to Ollama roles.
   */
  private mapRole(role: string | undefined): 'user' | 'assistant' | 'system' | 'tool' {
    switch (role) {
      case 'user':
        return 'user';
      case 'model':
        return 'assistant';
      case 'function':
        return 'tool';
      case 'system':
        return 'system';
      default:
        return 'user';
    }
  }

  /**
   * Checks if content contains function calls.
   */
  private hasFunctionCalls(content: Content): boolean {
    return content.parts?.some((part) => 'functionCall' in part && part.functionCall) ?? false;
  }

  /**
   * Checks if content contains function responses.
   */
  private hasFunctionResponse(content: Content): boolean {
    return (
      content.parts?.some((part) => 'functionResponse' in part && part.functionResponse) ?? false
    );
  }

  /**
   * Extracts text from content parts.
   */
  private extractText(content: Content): string {
    const textParts = content.parts
      ?.filter(
        (part): part is Part & { text: string } => 'text' in part && typeof part.text === 'string'
      )
      .map((part) => part.text);
    return textParts?.join('') ?? '';
  }

  /**
   * Extracts text from a ContentUnion (Content, Part, or string) for system instruction.
   */
  private extractTextFromContent(content: unknown): string {
    if (typeof content === 'string') {
      return content;
    }
    // Handle Part type (has text property directly)
    if (
      content &&
      typeof content === 'object' &&
      'text' in content &&
      typeof (content as Part).text === 'string'
    ) {
      return (content as Part).text as string;
    }
    // Handle Content type (has parts array)
    if (content && typeof content === 'object' && 'parts' in content) {
      return this.extractText(content as Content);
    }
    return '';
  }

  /**
   * Extracts tool calls from content parts.
   */
  private extractToolCalls(content: Content): OllamaToolCall[] {
    const functionCalls = content.parts?.filter(
      (part): part is Part & { functionCall: FunctionCall } =>
        'functionCall' in part && part.functionCall !== undefined
    );

    return (
      functionCalls?.map((part) => ({
        function: {
          name: part.functionCall.name ?? '',
          arguments: (part.functionCall.args as Record<string, unknown>) ?? {},
        },
      })) ?? []
    );
  }

  /**
   * Extracts function responses from content parts.
   */
  private extractFunctionResponses(content: Content): FunctionResponse[] {
    const functionResponses = content.parts?.filter(
      (part): part is Part & { functionResponse: FunctionResponse } =>
        'functionResponse' in part && part.functionResponse !== undefined
    );

    return functionResponses?.map((part) => part.functionResponse) ?? [];
  }

  /**
   * Converts ADK toolsDict to Ollama Tool[].
   *
   * Extracts function declarations from BaseTool instances and
   * converts them to Ollama's tool format.
   *
   * @param toolsDict - Dictionary of ADK tools
   * @returns Array of Ollama Tool objects
   */
  private convertTools(toolsDict: { [key: string]: BaseTool }): OllamaTool[] {
    if (!toolsDict || Object.keys(toolsDict).length === 0) {
      agentLogger.debug('[OllamaLlm] No tools in toolsDict');
      return [];
    }

    agentLogger.debug(`[OllamaLlm] toolsDict keys: ${Object.keys(toolsDict).join(', ')}`);
    const tools: OllamaTool[] = [];

    for (const [name, tool] of Object.entries(toolsDict)) {
      const declaration = tool._getDeclaration?.();
      if (!declaration) {
        agentLogger.debug(`[OllamaLlm] Tool ${name} has no declaration, skipping`);
        continue;
      }

      agentLogger.debug(`[OllamaLlm] Adding tool: ${declaration.name}`);
      agentLogger.debug(
        `[OllamaLlm] Tool ${declaration.name} parameters: ${JSON.stringify(declaration.parameters)}`
      );
      tools.push({
        type: 'function',
        function: {
          name: declaration.name,
          description: declaration.description,
          parameters: declaration.parameters as OllamaTool['function']['parameters'],
        },
      });
    }

    return tools;
  }

  /**
   * Converts Ollama response to ADK LlmResponse.
   *
   * @param response - Ollama ChatResponse
   * @param partial - Whether this is a partial streaming response
   * @returns ADK LlmResponse
   */
  private convertToLlmResponse(response: OllamaChatResponse, partial: boolean): LlmResponse {
    const parts: Part[] = [];

    // Add text content if present
    if (response.message.content) {
      parts.push({ text: response.message.content });
    }

    // Add function calls if present
    let hasToolCalls = false;
    if (response.message.tool_calls && response.message.tool_calls.length > 0) {
      hasToolCalls = true;
      for (const toolCall of response.message.tool_calls) {
        parts.push({
          functionCall: {
            name: toolCall.function.name,
            args: toolCall.function.arguments,
          },
        });
      }
    }

    // Ensure we always have at least an empty text part
    if (parts.length === 0) {
      parts.push({ text: '' });
    }

    const content: Content = {
      role: 'model',
      parts,
    };

    // When there are tool calls, turnComplete should be false so ADK continues processing
    // Only mark turnComplete when there are no tool calls and Ollama says done
    return {
      content,
      partial,
      turnComplete: response.done && !hasToolCalls,
    };
  }
}

/**
 * Registers OllamaLlm with the ADK LLMRegistry.
 *
 * This allows agents to use Ollama models by specifying model names
 * with the 'ollama/' prefix (e.g., 'ollama/llama3.2').
 */
export function registerOllamaLlm(): void {
  LLMRegistry.register(OllamaLlm);
}

// Auto-register when this module is imported
registerOllamaLlm();
