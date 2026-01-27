/**
 * MCP Agent (ADK)
 *
 * External tool integration specialist using Model Context Protocol (MCP).
 * Connects to configured MCP servers to access documentation, file systems,
 * and other external capabilities. Tools are dynamically discovered from
 * connected servers.
 *
 * Common use cases:
 * - Documentation lookup (resolve-library-id, query-docs)
 * - File operations (read_file, write_file, list_directory)
 * - Custom integrations defined in app_settings.yaml
 *
 * Dependencies:
 * - @google/adk: LlmAgent for ADK-compatible agent
 * - @modelcontextprotocol/sdk: Official MCP client implementation
 */
import { LlmAgent } from '@google/adk';
import type { AppSettings } from '../config/index.js';
import { getAdkModelName, getAgentPrompt, loadSettings } from '../config/index.js';
import { getMcpManager } from '../mcp/index.js';
import { saveMemoriesOnFinalResponse } from '../memory/callbacks.js';
import { createMcpAdkTools } from '../tools/mcp-adk-adapter.js';

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

// Load settings with fallback
let settings: AppSettings | null;
try {
  settings = loadSettings();
} catch {
  settings = null;
}

const modelName = settings ? getAdkModelName('mcp_agent', settings) : 'gemini-2.5-flash';

const customPrompt = settings ? getAgentPrompt('mcp_agent', settings) : undefined;

/**
 * MCP Agent placeholder - tools are loaded dynamically
 * Use createMcpAgent() to get a fully initialized agent with MCP tools
 */
export const mcpAgent = new LlmAgent({
  name: 'mcp_agent',
  model: modelName,
  description:
    'MCP tools specialist for documentation lookup, file operations, and external integrations.',
  instruction: customPrompt ?? DEFAULT_INSTRUCTION,
  tools: [], // Tools are loaded dynamically via createMcpAgent
  afterModelCallback: saveMemoriesOnFinalResponse,
});

/**
 * Creates a fully initialized MCP agent with dynamically discovered tools
 * @returns LlmAgent configured with MCP tools
 */
export async function createMcpAgent(): Promise<LlmAgent> {
  // Load MCP tools dynamically
  const mcpTools = await createMcpAdkTools();

  // Create a new agent with the discovered tools
  return new LlmAgent({
    name: 'mcp_agent',
    model: modelName,
    description:
      'MCP tools specialist for documentation lookup, file operations, and external integrations.',
    instruction: customPrompt ?? DEFAULT_INSTRUCTION,
    tools: mcpTools,
    afterModelCallback: saveMemoriesOnFinalResponse,
  });
}

// Legacy tool executors export for backwards compatibility
export const mcpToolExecutors = {
  async execute(toolName: string, args: Record<string, unknown>): Promise<string> {
    const mcpManager = getMcpManager();
    return mcpManager.callTool(toolName, args);
  },
};
