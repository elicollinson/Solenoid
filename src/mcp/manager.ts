/**
 * MCP Manager
 *
 * Manages connections to Model Context Protocol (MCP) servers. Handles
 * server discovery from configuration, connection establishment (stdio or HTTP),
 * tool discovery, and tool invocation. Supports multiple concurrent server
 * connections with namespaced tool names.
 *
 * Dependencies:
 * - @modelcontextprotocol/sdk: Official MCP client SDK for server communication
 *   - StdioClientTransport: Connects to MCP servers via subprocess stdio
 *   - StreamableHTTPClientTransport: Connects to MCP servers via HTTP
 */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import type { ToolDefinition } from '../llm/types.js';
import { loadSettings } from '../config/index.js';
import type { McpServer, McpStdioServer } from '../config/schema.js';
import { serverLogger } from '../utils/logger.js';

interface McpTool {
  serverName: string;
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export class McpManager {
  private clients: Map<string, Client> = new Map();
  private tools: Map<string, McpTool> = new Map();
  private initialized = false;

  async initialize(): Promise<void> {
    if (this.initialized) return;

    let settings;
    try {
      settings = loadSettings();
    } catch {
      serverLogger.warn('MCP: No settings found, skipping MCP server connections');
      this.initialized = true;
      return;
    }

    const servers = settings.mcp_servers;
    for (const [name, config] of Object.entries(servers)) {
      try {
        await this.connectServer(name, config);
      } catch (error) {
        serverLogger.warn({ error }, `MCP: Failed to connect to ${name}`);
      }
    }

    this.initialized = true;
  }

  private async connectServer(name: string, config: McpServer): Promise<void> {
    const client = new Client({
      name: `solenoid-${name}`,
      version: '2.0.0',
    });

    let transport;

    if (this.isStdioServer(config)) {
      transport = new StdioClientTransport({
        command: config.command,
        args: config.args,
        env: config.env,
      });
    } else {
      transport = new StreamableHTTPClientTransport(new URL(config.url), {
        requestInit: {
          headers: config.headers,
        },
      });
    }

    await client.connect(transport);
    this.clients.set(name, client);

    // Discover tools
    const toolsList = await client.listTools();
    for (const tool of toolsList.tools) {
      const fullName = `${name}_${tool.name}`;
      this.tools.set(fullName, {
        serverName: name,
        name: tool.name,
        description: tool.description ?? '',
        inputSchema: tool.inputSchema as Record<string, unknown>,
      });
    }

    serverLogger.info(`MCP: Connected to ${name} with ${toolsList.tools.length} tools`);
  }

  private isStdioServer(config: McpServer): config is McpStdioServer {
    return 'command' in config;
  }

  getToolDefinitions(): ToolDefinition[] {
    const definitions: ToolDefinition[] = [];

    for (const [fullName, tool] of this.tools) {
      definitions.push({
        type: 'function',
        function: {
          name: fullName,
          description: `[MCP:${tool.serverName}] ${tool.description}`,
          parameters: {
            type: 'object',
            properties: (tool.inputSchema as { properties?: Record<string, unknown> })
              .properties as Record<string, { type: string; description: string }> ?? {},
            required: (tool.inputSchema as { required?: string[] }).required,
          },
        },
      });
    }

    return definitions;
  }

  async callTool(fullName: string, args: Record<string, unknown>): Promise<string> {
    const tool = this.tools.get(fullName);
    if (!tool) {
      return `Error: Unknown MCP tool: ${fullName}`;
    }

    const client = this.clients.get(tool.serverName);
    if (!client) {
      return `Error: MCP server not connected: ${tool.serverName}`;
    }

    try {
      const result = await client.callTool({
        name: tool.name,
        arguments: args,
      });

      // Extract text content from result
      const content = result.content as Array<{ type: string; text?: string }>;
      const textContent = content
        .filter((c): c is { type: 'text'; text: string } => c.type === 'text' && typeof c.text === 'string')
        .map((c) => c.text)
        .join('\n');

      return textContent || JSON.stringify(result.content);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      return `Error calling MCP tool ${fullName}: ${message}`;
    }
  }

  async close(): Promise<void> {
    for (const [name, client] of this.clients) {
      try {
        await client.close();
      } catch (error) {
        serverLogger.warn({ error }, `MCP: Error closing ${name}`);
      }
    }
    this.clients.clear();
    this.tools.clear();
    this.initialized = false;
  }

  getToolNames(): string[] {
    return Array.from(this.tools.keys());
  }
}

let defaultManager: McpManager | null = null;

export function getMcpManager(): McpManager {
  if (!defaultManager) {
    defaultManager = new McpManager();
  }
  return defaultManager;
}

export async function closeMcpManager(): Promise<void> {
  if (defaultManager) {
    await defaultManager.close();
    defaultManager = null;
  }
}
