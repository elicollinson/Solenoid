import type {
  Agent,
  AgentConfig,
  AgentContext,
  AgentRequest,
  AgentStreamResponse,
} from './types.js';
import type { Message, ToolDefinition, LLMProvider } from '../llm/types.js';
import { getOllamaProvider } from '../llm/ollama.js';

export class BaseAgent implements Agent {
  readonly name: string;
  readonly config: AgentConfig;
  private llm: LLMProvider;
  private subAgentMap: Map<string, Agent> = new Map();

  constructor(config: AgentConfig, llm?: LLMProvider) {
    this.name = config.name;
    this.config = config;
    this.llm = llm ?? getOllamaProvider();

    if (config.subAgents) {
      for (const subAgent of config.subAgents) {
        this.subAgentMap.set(subAgent.name, subAgent);
      }
    }
  }

  async *run(request: AgentRequest): AgentStreamResponse {
    let currentRequest = request;

    if (this.config.beforeModelCallback) {
      const result = await this.config.beforeModelCallback(currentRequest);
      if (result === null) {
        yield { type: 'done' };
        return;
      }
      currentRequest = result;
    }

    const instruction = this.getInstruction(currentRequest.context);
    const tools = this.buildTools();

    let fullContent = '';

    for await (const chunk of this.llm.chatStream({
      model: this.config.model,
      messages: currentRequest.messages,
      systemPrompt: instruction,
      tools,
    })) {
      if (chunk.message.content) {
        fullContent += chunk.message.content;
        yield { type: 'text', content: chunk.message.content };
      }

      if (chunk.message.tool_calls && chunk.message.tool_calls.length > 0) {
        for (const toolCall of chunk.message.tool_calls) {
          const toolName = toolCall.function.name;

          if (toolName.startsWith('transfer_to_')) {
            const targetAgent = toolName.replace('transfer_to_', '');
            const subAgent = this.subAgentMap.get(targetAgent);

            if (subAgent) {
              yield { type: 'transfer', transferTo: targetAgent };

              const subRequest: AgentRequest = {
                messages: [
                  ...currentRequest.messages,
                  { role: 'assistant', content: fullContent },
                ],
                context: {
                  ...currentRequest.context,
                  parentAgent: this.name,
                },
              };

              for await (const subChunk of subAgent.run(subRequest)) {
                yield subChunk;
              }
              return;
            }
          }

          yield { type: 'tool_call', toolCall };
        }
      }

      if (chunk.done) {
        break;
      }
    }

    const responseMessage: Message = {
      role: 'assistant',
      content: fullContent,
    };

    if (this.config.afterModelCallback) {
      await this.config.afterModelCallback(currentRequest, responseMessage);
    }

    yield { type: 'done' };
  }

  private getInstruction(context: AgentContext): string {
    if (typeof this.config.instruction === 'function') {
      return this.config.instruction(context);
    }
    return this.config.instruction;
  }

  private buildTools(): ToolDefinition[] {
    const tools: ToolDefinition[] = [...(this.config.tools ?? [])];

    for (const subAgent of this.subAgentMap.values()) {
      tools.push({
        type: 'function',
        function: {
          name: `transfer_to_${subAgent.name}`,
          description: `Transfer control to ${subAgent.name}`,
          parameters: {
            type: 'object',
            properties: {},
          },
        },
      });
    }

    return tools;
  }
}
