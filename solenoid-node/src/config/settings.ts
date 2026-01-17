
/**
 * Settings Loader
 *
 * Loads and caches application configuration from app_settings.yaml. Searches
 * for the config file starting from the current directory up to root. Provides
 * helper functions to get model configs and agent prompts with fallback defaults.
 *
 * Dependencies:
 * - yaml: YAML parser for reading configuration files
 */
import { readFileSync, writeFileSync, existsSync, copyFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { parse as parseYaml, stringify as stringifyYaml } from 'yaml';
import {
  AppSettingsSchema,
  type AppSettings,
  type ModelConfig,
  type AgentName,
  AGENT_NAMES,
} from './schema.js';

const DEFAULT_SETTINGS_FILENAME = 'app_settings.yaml';

let cachedSettings: AppSettings | null = null;
let cachedRawSettings: Record<string, unknown> | null = null;
let settingsPath: string | null = null;

export function findSettingsFile(startDir: string = process.cwd()): string | null {
  let dir = startDir;
  const root = dirname(dir);

  while (dir !== root) {
    const candidate = resolve(dir, DEFAULT_SETTINGS_FILENAME);
    if (existsSync(candidate)) {
      return candidate;
    }
    dir = dirname(dir);
  }

  const rootCandidate = resolve(root, DEFAULT_SETTINGS_FILENAME);
  if (existsSync(rootCandidate)) {
    return rootCandidate;
  }

  return null;
}

export function loadSettings(path?: string): AppSettings {
  const configPath = path ?? findSettingsFile();

  if (!configPath) {
    throw new Error(
      `Configuration file not found. Create ${DEFAULT_SETTINGS_FILENAME} or specify a path.`
    );
  }

  if (cachedSettings && settingsPath === configPath) {
    return cachedSettings;
  }

  const content = readFileSync(configPath, 'utf-8');
  const raw = parseYaml(content) as Record<string, unknown>;
  const result = AppSettingsSchema.safeParse(raw);

  if (!result.success) {
    const errors = result.error.errors
      .map((e) => `  - ${e.path.join('.')}: ${e.message}`)
      .join('\n');
    throw new Error(`Invalid configuration in ${configPath}:\n${errors}`);
  }

  cachedSettings = result.data;
  cachedRawSettings = raw;
  settingsPath = configPath;

  return result.data;
}

export function getModelConfig(agentName: AgentName, settings?: AppSettings): ModelConfig {
  const config = settings ?? loadSettings();

  const agentConfig = config.models.agents?.[agentName];
  if (agentConfig) {
    return {
      name: agentConfig.name ?? config.models.default.name,
      provider: agentConfig.provider ?? config.models.default.provider,
      context_length: agentConfig.context_length ?? config.models.default.context_length,
    };
  }

  return config.models.default;
}

export function getAgentPrompt(
  agentName: AgentName,
  settings?: AppSettings,
  variables?: Record<string, string>
): string | undefined {
  const config = settings ?? loadSettings();
  let prompt = config.agent_prompts[agentName];

  if (prompt && variables) {
    for (const [key, value] of Object.entries(variables)) {
      prompt = prompt.replace(new RegExp(`\\{${key}\\}`, 'g'), value);
    }
  }

  return prompt;
}

export function clearSettingsCache(): void {
  cachedSettings = null;
  cachedRawSettings = null;
  settingsPath = null;
}

export function isValidAgentName(name: string): name is AgentName {
  return AGENT_NAMES.includes(name as AgentName);
}

/**
 * Get the current settings file path
 */
export function getSettingsPath(): string | null {
  if (settingsPath) return settingsPath;
  // Try to find it if not cached
  return findSettingsFile();
}

/**
 * Get raw settings without schema validation (for dynamic section discovery)
 * Returns null if no settings file found
 */
export function getRawSettings(): Record<string, unknown> | null {
  if (cachedRawSettings) return cachedRawSettings;

  const configPath = getSettingsPath();
  if (!configPath) return null;

  try {
    const content = readFileSync(configPath, 'utf-8');
    cachedRawSettings = parseYaml(content) as Record<string, unknown>;
    settingsPath = configPath;
    return cachedRawSettings;
  } catch {
    return null;
  }
}

/**
 * Save settings to file with backup
 */
export function saveSettings(settings: Record<string, unknown>): void {
  const configPath = getSettingsPath();
  if (!configPath) {
    throw new Error('No settings file found to save to');
  }

  // Create backup
  const backupPath = `${configPath}.backup`;
  if (existsSync(configPath)) {
    copyFileSync(configPath, backupPath);
  }

  // Write new settings
  const yaml = stringifyYaml(settings, {
    indent: 2,
    lineWidth: 0, // Don't wrap lines
  });

  writeFileSync(configPath, yaml, 'utf-8');

  // Update cache
  cachedRawSettings = settings;
  cachedSettings = null; // Clear validated cache so it reloads
}
