/**
 * Extensible settings validator that validates YAML sections against inferred schemas.
 *
 * The validator works by:
 * 1. Using Zod schemas for base validation
 * 2. Allowing custom validators to be registered for specific sections
 * 3. Providing detailed error messages with paths
 */

import { z, type ZodError } from 'zod';
import { parse as parseYaml, YAMLParseError } from 'yaml';
import {
  AppSettingsSchema,
  ModelsConfigSchema,
  SearchConfigSchema,
  McpServerSchema,
  AgentPromptsSchema,
  EmbeddingsConfigSchema,
  type AppSettings,
} from './schema.js';

export interface ValidationError {
  path: string;
  message: string;
  value?: unknown;
}

export interface ValidationResult {
  isValid: boolean;
  errors: ValidationError[];
  parsedValue?: unknown;
}

export type CustomValidator = (value: unknown, reference?: unknown) => ValidationResult;

// Section key type
export type SectionKey = keyof AppSettings;

// Section info for UI display
export interface SectionInfo {
  key: SectionKey;
  displayName: string;
  description: string;
}

// Section metadata for the UI
export const SECTION_INFO: Record<SectionKey, SectionInfo> = {
  models: {
    key: 'models',
    displayName: 'Models',
    description: 'Configure model settings (defaults and per-agent overrides)',
  },
  search: {
    key: 'search',
    displayName: 'Search',
    description: 'Configure web search provider and API keys',
  },
  mcp_servers: {
    key: 'mcp_servers',
    displayName: 'MCP Servers',
    description: 'Configure Model Context Protocol server connections',
  },
  agent_prompts: {
    key: 'agent_prompts',
    displayName: 'Agent Prompts',
    description: 'Configure system prompts for each agent',
  },
  embeddings: {
    key: 'embeddings',
    displayName: 'Embeddings',
    description: 'Configure embedding model settings',
  },
};

// Map section keys to their Zod schemas
const SECTION_SCHEMAS: Record<SectionKey, z.ZodType<unknown>> = {
  models: ModelsConfigSchema,
  search: SearchConfigSchema,
  mcp_servers: z.record(z.string(), McpServerSchema),
  agent_prompts: AgentPromptsSchema,
  embeddings: EmbeddingsConfigSchema,
};

// Custom validators registry
const customValidators: Map<SectionKey, CustomValidator> = new Map();

/**
 * Register a custom validator for a specific settings section.
 */
export function registerValidator(sectionKey: SectionKey, validator: CustomValidator): void {
  customValidators.set(sectionKey, validator);
}

/**
 * Convert Zod errors to our ValidationError format.
 */
function zodErrorsToValidationErrors(zodError: ZodError): ValidationError[] {
  return zodError.errors.map((err) => ({
    path: err.path.join('.'),
    message: err.message,
  }));
}

/**
 * Validate a YAML string can be parsed.
 */
export function validateYamlString(yamlString: string): ValidationResult {
  try {
    const parsed = parseYaml(yamlString);
    return {
      isValid: true,
      errors: [],
      parsedValue: parsed,
    };
  } catch (error) {
    if (error instanceof YAMLParseError) {
      const lineInfo = error.linePos
        ? `Line ${error.linePos[0].line}, column ${error.linePos[0].col}: `
        : '';
      return {
        isValid: false,
        errors: [
          {
            path: '',
            message: `Invalid YAML syntax: ${lineInfo}${error.message}`,
          },
        ],
      };
    }
    return {
      isValid: false,
      errors: [
        {
          path: '',
          message: `Invalid YAML: ${error instanceof Error ? error.message : 'Unknown error'}`,
        },
      ],
    };
  }
}

/**
 * Validate a specific settings section.
 */
export function validateSection(
  sectionKey: SectionKey,
  yamlString: string,
  _referenceSettings?: AppSettings
): ValidationResult {
  // First parse the YAML
  const parseResult = validateYamlString(yamlString);
  if (!parseResult.isValid) {
    return parseResult;
  }

  const parsed = parseResult.parsedValue;

  // Check for custom validator first
  const customValidator = customValidators.get(sectionKey);
  if (customValidator) {
    return customValidator(parsed, _referenceSettings?.[sectionKey]);
  }

  // Use Zod schema validation
  const schema = SECTION_SCHEMAS[sectionKey];
  if (!schema) {
    return {
      isValid: true,
      errors: [],
      parsedValue: parsed,
    };
  }

  const result = schema.safeParse(parsed);
  if (!result.success) {
    return {
      isValid: false,
      errors: zodErrorsToValidationErrors(result.error),
    };
  }

  return {
    isValid: true,
    errors: [],
    parsedValue: result.data,
  };
}

/**
 * Validate the entire settings object.
 */
export function validateSettings(yamlString: string): ValidationResult {
  const parseResult = validateYamlString(yamlString);
  if (!parseResult.isValid) {
    return parseResult;
  }

  const result = AppSettingsSchema.safeParse(parseResult.parsedValue);
  if (!result.success) {
    return {
      isValid: false,
      errors: zodErrorsToValidationErrors(result.error),
    };
  }

  return {
    isValid: true,
    errors: [],
    parsedValue: result.data,
  };
}

// ============================================================================
// Built-in Custom Validators for Specific Sections
// ============================================================================

/**
 * Custom validator for the 'models' section with model-specific rules.
 */
function validateModelsSection(value: unknown, _reference?: unknown): ValidationResult {
  const errors: ValidationError[] = [];

  if (!value || typeof value !== 'object') {
    return {
      isValid: false,
      errors: [{ path: '', message: 'Models section must be an object' }],
    };
  }

  const models = value as Record<string, unknown>;

  // Validate each model entry
  for (const [modelKey, modelConfig] of Object.entries(models)) {
    if (modelKey === 'agents') {
      // Handle the nested agents subsection
      if (modelConfig && typeof modelConfig !== 'object') {
        errors.push({
          path: 'agents',
          message: 'agents subsection must be an object',
        });
        continue;
      }

      if (modelConfig) {
        for (const [agentName, agentModelConfig] of Object.entries(
          modelConfig as Record<string, unknown>
        )) {
          validateModelConfig(agentModelConfig, `agents.${agentName}`, errors);
        }
      }
    } else {
      // Regular model config (default, agent, extractor, etc.)
      validateModelConfig(modelConfig, modelKey, errors);
    }
  }

  // Also validate with Zod for complete validation
  const zodResult = ModelsConfigSchema.safeParse(value);
  if (!zodResult.success) {
    errors.push(...zodErrorsToValidationErrors(zodResult.error));
  }

  return {
    isValid: errors.length === 0,
    errors,
    parsedValue: value,
  };
}

function validateModelConfig(
  config: unknown,
  path: string,
  errors: ValidationError[]
): void {
  if (!config || typeof config !== 'object') {
    errors.push({
      path,
      message: 'Model configuration must be an object',
    });
    return;
  }

  const modelConfig = config as Record<string, unknown>;

  // Check for required 'name' field (except for partial configs in agents)
  if (path === 'default' && !modelConfig.name) {
    errors.push({
      path,
      message: "Model configuration must have a 'name' field",
    });
  }

  // Validate context_length if present
  if ('context_length' in modelConfig) {
    const ctx = modelConfig.context_length;
    if (typeof ctx !== 'number' || ctx <= 0 || !Number.isInteger(ctx)) {
      errors.push({
        path: `${path}.context_length`,
        message: 'context_length must be a positive integer',
      });
    }
  }

  // Validate provider if present
  if ('provider' in modelConfig) {
    const provider = modelConfig.provider;
    const validProviders = ['ollama_chat', 'ollama', 'openai', 'anthropic', 'litellm'];
    if (typeof provider !== 'string' || !validProviders.includes(provider)) {
      errors.push({
        path: `${path}.provider`,
        message: `Invalid provider. Must be one of: ${validProviders.join(', ')}`,
      });
    }
  }
}

/**
 * Custom validator for the 'search' section.
 */
function validateSearchSection(value: unknown, _reference?: unknown): ValidationResult {
  const errors: ValidationError[] = [];

  if (!value || typeof value !== 'object') {
    return {
      isValid: false,
      errors: [{ path: '', message: 'Search section must be an object' }],
    };
  }

  const search = value as Record<string, unknown>;

  // Validate provider
  if ('provider' in search) {
    const validProviders = ['brave', 'google', 'duckduckgo', 'serper', 'none'];
    if (typeof search.provider !== 'string' || !validProviders.includes(search.provider)) {
      errors.push({
        path: 'provider',
        message: `Invalid search provider. Must be one of: ${validProviders.join(', ')}`,
      });
    }
  }

  return {
    isValid: errors.length === 0,
    errors,
    parsedValue: value,
  };
}

/**
 * Custom validator for the 'mcp_servers' section.
 */
function validateMcpServersSection(value: unknown, _reference?: unknown): ValidationResult {
  const errors: ValidationError[] = [];

  if (!value || typeof value !== 'object') {
    return {
      isValid: false,
      errors: [{ path: '', message: 'MCP servers section must be an object' }],
    };
  }

  const servers = value as Record<string, unknown>;

  for (const [serverName, serverConfig] of Object.entries(servers)) {
    if (!serverConfig || typeof serverConfig !== 'object') {
      errors.push({
        path: serverName,
        message: 'MCP server configuration must be an object',
      });
      continue;
    }

    const config = serverConfig as Record<string, unknown>;
    const serverType = config.type ?? 'stdio';

    if (serverType === 'http') {
      // HTTP servers need a url
      if (!config.url) {
        errors.push({
          path: serverName,
          message: "HTTP MCP server must have a 'url' field",
        });
      }
    } else {
      // stdio servers need a command
      if (!config.command) {
        errors.push({
          path: serverName,
          message: "MCP server must have a 'command' field",
        });
      }
    }
  }

  return {
    isValid: errors.length === 0,
    errors,
    parsedValue: value,
  };
}

/**
 * Custom validator for the 'agent_prompts' section.
 */
function validateAgentPromptsSection(value: unknown, _reference?: unknown): ValidationResult {
  const errors: ValidationError[] = [];

  if (!value || typeof value !== 'object') {
    return {
      isValid: false,
      errors: [{ path: '', message: 'Agent prompts section must be an object' }],
    };
  }

  const prompts = value as Record<string, unknown>;

  for (const [agentName, prompt] of Object.entries(prompts)) {
    if (typeof prompt !== 'string') {
      errors.push({
        path: agentName,
        message: 'Agent prompt must be a string',
      });
      continue;
    }

    if (prompt.trim().length < 10) {
      errors.push({
        path: agentName,
        message: 'Agent prompt appears too short (less than 10 characters)',
      });
    }
  }

  return {
    isValid: errors.length === 0,
    errors,
    parsedValue: value,
  };
}

// Register built-in validators
registerValidator('models', validateModelsSection);
registerValidator('search', validateSearchSection);
registerValidator('mcp_servers', validateMcpServersSection);
registerValidator('agent_prompts', validateAgentPromptsSection);
