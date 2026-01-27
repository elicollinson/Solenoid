/**
 * MCP to ADK Tool Adapter
 *
 * Converts MCP (Model Context Protocol) tools to ADK FunctionTool format
 * dynamically. This allows MCP tools discovered from connected servers
 * to be used seamlessly with ADK LlmAgents.
 *
 * Dependencies:
 * - @google/adk: FunctionTool for ADK-compatible tool definitions
 * - @modelcontextprotocol/sdk: MCP client for tool discovery
 */
import { FunctionTool } from '@google/adk';
import { type ZodTypeAny, z } from 'zod';
import { getMcpManager } from '../mcp/index.js';

/**
 * JSON Schema type definition for MCP tool parameters
 */
interface JsonSchemaProperty {
  type?: string;
  description?: string;
  enum?: string[];
  items?: JsonSchemaProperty;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
}

interface JsonSchema {
  type?: string;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
}

/**
 * Converts a JSON Schema property to a Zod schema
 */
function jsonSchemaToZod(schema: JsonSchemaProperty): ZodTypeAny {
  if (!schema.type) {
    return z.unknown();
  }

  switch (schema.type) {
    case 'string':
      if (schema.enum) {
        return z.enum(schema.enum as [string, ...string[]]);
      }
      return z.string();
    case 'number':
    case 'integer':
      return z.number();
    case 'boolean':
      return z.boolean();
    case 'array':
      if (schema.items) {
        return z.array(jsonSchemaToZod(schema.items));
      }
      return z.array(z.unknown());
    case 'object':
      if (schema.properties) {
        const shape: Record<string, ZodTypeAny> = {};
        for (const [key, propSchema] of Object.entries(schema.properties)) {
          let zodProp = jsonSchemaToZod(propSchema);
          if (propSchema.description) {
            zodProp = zodProp.describe(propSchema.description);
          }
          // Make optional if not in required array
          if (!schema.required?.includes(key)) {
            zodProp = zodProp.optional();
          }
          shape[key] = zodProp;
        }
        return z.object(shape);
      }
      return z.record(z.unknown());
    default:
      return z.unknown();
  }
}

/**
 * Converts MCP tool input schema to Zod object schema
 */
function mcpSchemaToZodObject(inputSchema: JsonSchema): z.ZodObject<Record<string, ZodTypeAny>> {
  const shape: Record<string, ZodTypeAny> = {};

  if (inputSchema.properties) {
    for (const [key, propSchema] of Object.entries(inputSchema.properties)) {
      let zodProp = jsonSchemaToZod(propSchema);
      if (propSchema.description) {
        zodProp = zodProp.describe(propSchema.description);
      }
      // Make optional if not in required array
      if (!inputSchema.required?.includes(key)) {
        zodProp = zodProp.optional();
      }
      shape[key] = zodProp;
    }
  }

  return z.object(shape);
}

/**
 * Creates ADK FunctionTools from all discovered MCP tools
 * @returns Array of FunctionTool instances for use with LlmAgent
 */
export async function createMcpAdkTools(): Promise<FunctionTool[]> {
  const mcpManager = getMcpManager();

  // Ensure MCP manager is initialized
  await mcpManager.initialize();

  const toolNames = mcpManager.getToolNames();
  const tools: FunctionTool[] = [];

  for (const fullName of toolNames) {
    const toolDef = mcpManager.getToolDefinitions().find((t) => t.function.name === fullName);

    if (!toolDef) continue;

    const inputSchema: JsonSchema = {
      type: 'object',
      properties: toolDef.function.parameters.properties as Record<string, JsonSchemaProperty>,
      required: toolDef.function.parameters.required,
    };

    const zodParams = mcpSchemaToZodObject(inputSchema);

    const tool = new FunctionTool({
      name: fullName,
      description: toolDef.function.description,
      parameters: zodParams,
      execute: async (args) => {
        const result = await mcpManager.callTool(fullName, args as Record<string, unknown>);
        return { result };
      },
    });

    tools.push(tool);
  }

  return tools;
}

/**
 * Creates a single ADK FunctionTool from an MCP tool by name
 * @param toolName The full MCP tool name (e.g., 'context7_resolve-library-id')
 * @returns FunctionTool instance or null if tool not found
 */
export async function createMcpAdkTool(toolName: string): Promise<FunctionTool | null> {
  const mcpManager = getMcpManager();
  await mcpManager.initialize();

  const toolDef = mcpManager.getToolDefinitions().find((t) => t.function.name === toolName);

  if (!toolDef) return null;

  const inputSchema: JsonSchema = {
    type: 'object',
    properties: toolDef.function.parameters.properties as Record<string, JsonSchemaProperty>,
    required: toolDef.function.parameters.required,
  };

  const zodParams = mcpSchemaToZodObject(inputSchema);

  return new FunctionTool({
    name: toolName,
    description: toolDef.function.description,
    parameters: zodParams,
    execute: async (args) => {
      const result = await mcpManager.callTool(toolName, args as Record<string, unknown>);
      return { result };
    },
  });
}
