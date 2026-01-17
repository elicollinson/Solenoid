/**
 * Configuration Schema
 *
 * Zod validation schemas for app_settings.yaml. Defines the structure and
 * validation rules for all configuration sections including models, embeddings,
 * search providers, MCP servers, and custom agent prompts.
 *
 * Dependencies:
 * - zod: TypeScript-first schema validation with static type inference
 */
import { z } from 'zod';

export const EmbeddingsConfigSchema = z.object({
  provider: z.enum(['ollama', 'openai', 'transformers']).default('ollama'),
  host: z.string().url().default('http://localhost:11434'),
  model: z.string().default('nomic-embed-text'),
});

export const ModelConfigSchema = z.object({
  name: z.string(),
  provider: z.enum(['ollama_chat', 'openai', 'anthropic']).default('ollama_chat'),
  context_length: z.number().int().positive().default(128000),
});

export const ModelsConfigSchema = z.object({
  default: ModelConfigSchema,
  agent: ModelConfigSchema.optional(),
  extractor: ModelConfigSchema.partial().optional(),
  agents: z.record(z.string(), ModelConfigSchema.partial()).optional(),
});

export const SearchConfigSchema = z.object({
  provider: z.enum(['brave', 'google', 'none']).default('brave'),
  brave_search_api_key: z.string().optional(),
  google_api_key: z.string().optional(),
  google_cx: z.string().optional(),
});

export const McpStdioServerSchema = z.object({
  type: z.literal('stdio').optional().default('stdio'),
  command: z.string(),
  args: z.array(z.string()).default([]),
  env: z.record(z.string(), z.string()).optional(),
});

export const McpHttpServerSchema = z.object({
  type: z.literal('http'),
  url: z.string().url(),
  headers: z.record(z.string(), z.string()).optional(),
});

export const McpServerSchema = z.union([McpStdioServerSchema, McpHttpServerSchema]);

export const AgentPromptsSchema = z.record(z.string(), z.string());

export const AppSettingsSchema = z.object({
  embeddings: EmbeddingsConfigSchema.default({}),
  models: ModelsConfigSchema,
  search: SearchConfigSchema.default({}),
  mcp_servers: z.record(z.string(), McpServerSchema).default({}),
  agent_prompts: AgentPromptsSchema.default({}),
});

export type EmbeddingsConfig = z.infer<typeof EmbeddingsConfigSchema>;
export type ModelConfig = z.infer<typeof ModelConfigSchema>;
export type ModelsConfig = z.infer<typeof ModelsConfigSchema>;
export type SearchConfig = z.infer<typeof SearchConfigSchema>;
export type McpStdioServer = z.infer<typeof McpStdioServerSchema>;
export type McpHttpServer = z.infer<typeof McpHttpServerSchema>;
export type McpServer = z.infer<typeof McpServerSchema>;
export type AgentPrompts = z.infer<typeof AgentPromptsSchema>;
export type AppSettings = z.infer<typeof AppSettingsSchema>;

export const AGENT_NAMES = [
  'user_proxy_agent',
  'prime_agent',
  'planning_agent',
  'code_executor_agent',
  'chart_generator_agent',
  'research_agent',
  'mcp_agent',
  'generic_executor_agent',
] as const;

export type AgentName = (typeof AGENT_NAMES)[number];
