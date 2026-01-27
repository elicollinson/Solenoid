/**
 * Configuration Generator
 *
 * Generates app_settings.yaml with secrets loaded from environment variables.
 * This is useful for test harnesses and CI/CD environments where secrets
 * are provided via env vars rather than config files.
 *
 * Supported environment variables:
 * - BRAVE_SEARCH_API_KEY: Brave Search API key
 * - GOOGLE_API_KEY: Google API key (for search)
 * - GOOGLE_CX: Google Custom Search Engine ID
 * - OLLAMA_HOST: Ollama server URL
 * - OPENAI_API_KEY: OpenAI API key (for embeddings/models)
 * - ANTHROPIC_API_KEY: Anthropic API key
 */
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { stringify as stringifyYaml } from 'yaml';
import type { AppSettings } from './schema.js';

/**
 * Environment variable to settings path mapping
 */
export interface EnvMapping {
  envVar: string;
  settingsPath: string[];
  transform?: (value: string) => unknown;
}

/**
 * Default environment variable mappings
 */
export const DEFAULT_ENV_MAPPINGS: EnvMapping[] = [
  { envVar: 'BRAVE_SEARCH_API_KEY', settingsPath: ['search', 'brave_search_api_key'] },
  { envVar: 'GOOGLE_API_KEY', settingsPath: ['search', 'google_api_key'] },
  { envVar: 'GOOGLE_CX', settingsPath: ['search', 'google_cx'] },
  { envVar: 'OLLAMA_HOST', settingsPath: ['embeddings', 'host'] },
];

/**
 * Default settings template
 */
export function getDefaultSettings(): AppSettings {
  return {
    embeddings: {
      provider: 'ollama',
      host: 'http://localhost:11434',
      model: 'nomic-embed-text',
    },
    models: {
      default: {
        name: 'ministral-3:8b-instruct-2512-q4_K_M',
        provider: 'ollama_chat',
        context_length: 128000,
      },
    },
    search: {
      provider: 'brave',
      brave_search_api_key: '',
    },
    mcp_servers: {},
    agent_prompts: {},
  };
}

/**
 * Options for generating settings
 */
export interface GenerateSettingsOptions {
  /**
   * Base settings to start from. If not provided, uses default settings.
   */
  baseSettings?: Partial<AppSettings>;

  /**
   * Custom environment variable mappings. If not provided, uses default mappings.
   * Set to empty array to disable env var loading.
   */
  envMappings?: EnvMapping[];

  /**
   * Additional environment variables to inject (key-value pairs).
   * These are applied after the standard mappings.
   */
  additionalEnvVars?: Record<string, { settingsPath: string[]; value: string }>;

  /**
   * If true, only include env vars that are actually set.
   * If false, include all default settings even if env vars are not set.
   * Default: false
   */
  onlySetEnvVars?: boolean;
}

/**
 * Set a nested value in an object using a path array
 */
function setNestedValue(obj: Record<string, unknown>, path: string[], value: unknown): void {
  if (path.length === 0) return;

  let current = obj;
  for (let i = 0; i < path.length - 1; i++) {
    const key = path[i]!;
    if (!(key in current) || typeof current[key] !== 'object' || current[key] === null) {
      current[key] = {};
    }
    current = current[key] as Record<string, unknown>;
  }
  const finalKey = path[path.length - 1]!;
  current[finalKey] = value;
}

/**
 * Generate settings with environment variables injected
 */
export function generateSettings(options: GenerateSettingsOptions = {}): AppSettings {
  const {
    baseSettings,
    envMappings = DEFAULT_ENV_MAPPINGS,
    additionalEnvVars,
    onlySetEnvVars = false,
  } = options;

  // Start with default settings or provided base
  const settings = onlySetEnvVars
    ? ({ ...baseSettings } as Record<string, unknown>)
    : { ...getDefaultSettings(), ...baseSettings };

  // Apply environment variable mappings
  for (const mapping of envMappings) {
    const envValue = process.env[mapping.envVar];
    if (envValue !== undefined && envValue !== '') {
      const value = mapping.transform ? mapping.transform(envValue) : envValue;
      setNestedValue(settings as Record<string, unknown>, mapping.settingsPath, value);
    }
  }

  // Apply additional env vars
  if (additionalEnvVars) {
    for (const [, config] of Object.entries(additionalEnvVars)) {
      setNestedValue(settings as Record<string, unknown>, config.settingsPath, config.value);
    }
  }

  return settings as AppSettings;
}

/**
 * Options for writing settings to a file
 */
export interface WriteSettingsOptions extends GenerateSettingsOptions {
  /**
   * Path to write the settings file to.
   * Default: './app_settings.yaml' (current working directory)
   */
  outputPath?: string;

  /**
   * If true, create parent directories if they don't exist.
   * Default: true
   */
  createDirs?: boolean;

  /**
   * If true, overwrite existing file.
   * Default: true
   */
  overwrite?: boolean;
}

/**
 * Generate and write settings to a YAML file
 *
 * @returns The path to the written file
 */
export function writeSettingsFile(options: WriteSettingsOptions = {}): string {
  const {
    outputPath = './app_settings.yaml',
    createDirs = true,
    overwrite = true,
    ...generateOptions
  } = options;

  const resolvedPath = resolve(outputPath);

  // Check if file exists and we shouldn't overwrite
  if (!overwrite && existsSync(resolvedPath)) {
    return resolvedPath;
  }

  // Create parent directories if needed
  if (createDirs) {
    const dir = dirname(resolvedPath);
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
  }

  // Generate settings
  const settings = generateSettings(generateOptions);

  // Write to file
  const yaml = stringifyYaml(settings, {
    indent: 2,
    lineWidth: 0, // Don't wrap lines
  });

  writeFileSync(resolvedPath, yaml, 'utf-8');

  return resolvedPath;
}

/**
 * Get a summary of which env vars are set and would be injected
 */
export function getEnvVarStatus(
  envMappings: EnvMapping[] = DEFAULT_ENV_MAPPINGS
): Record<string, boolean> {
  const status: Record<string, boolean> = {};
  for (const mapping of envMappings) {
    const envValue = process.env[mapping.envVar];
    status[mapping.envVar] = envValue !== undefined && envValue !== '';
  }
  return status;
}
