import { BaseAgent } from './base-agent.js';
import type { Agent } from './types.js';
import { getAgentPrompt, getModelConfig, loadSettings } from '../config/index.js';
import { getMcpManager } from '../mcp/index.js';

const DEFAULT_INSTRUCTION = `You are an MCP tools specialist. You MUST use the tools provided to you.

### CRITICAL RULES
1. You MUST call one of your available tools. Do NOT make up tool names.
2. Look at your function interface to see the EXACT tool names available.
3. For documentation requests, use "resolve-library-id" first, then "query-docs".
4. For file operations, use tools like "read_file", "write_file", "list_directory".
5. NEVER invent tool names.
6. If you cannot find a suitable tool, respond with "Could Not Complete" status.

### TOOL CALL FORMAT
When calling tools, ensure your arguments are valid JSON:
- Use double quotes for strings
- No trailing commas
- Complete all brackets

### QUICK ACTION
- If you have no tools for the task, say "Could Not Complete" immediately.
- Do not loop or retry if tools are unavailable.

### OUTPUT FORMAT
After calling tools and getting results, format your response as:

## Result
[Summarize what you found from the tool calls]

## Status
Success / Partial / Could Not Complete`;

export async function createMcpAgent(): Promise<Agent> {
  let settings;
  try {
    settings = loadSettings();
  } catch {
    settings = null;
  }

  const modelConfig = settings
    ? getModelConfig('mcp_agent', settings)
    : { name: 'llama3.1:8b', provider: 'ollama_chat' as const, context_length: 128000 };

  const customPrompt = settings ? getAgentPrompt('mcp_agent', settings) : undefined;

  // Initialize MCP manager and get tools
  const mcpManager = getMcpManager();
  await mcpManager.initialize();
  const mcpTools = mcpManager.getToolDefinitions();

  return new BaseAgent({
    name: 'mcp_agent',
    model: modelConfig.name,
    instruction: customPrompt ?? DEFAULT_INSTRUCTION,
    tools: mcpTools,
    disallowTransferToParent: true,
  });
}

export const mcpToolExecutors = {
  async execute(toolName: string, args: Record<string, unknown>): Promise<string> {
    const mcpManager = getMcpManager();
    return mcpManager.callTool(toolName, args);
  },
};
