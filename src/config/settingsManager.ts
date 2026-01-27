import { parse as parseYaml, stringify as stringifyYaml } from 'yaml';
import { clearSettingsCache, getRawSettings, getSettingsPath, saveSettings } from './settings.js';
import { type ValidationResult, hasValidator, validateSection } from './validator.js';

export interface SectionInfo {
  key: string;
  displayName: string;
  description: string;
  hasValidator: boolean;
}

// Known section metadata (for display only)
const KNOWN_SECTIONS: Record<string, { displayName: string; description: string }> = {
  models: { displayName: 'Models', description: 'Model configurations' },
  search: { displayName: 'Search', description: 'Web search provider' },
  mcp_servers: { displayName: 'MCP Servers', description: 'MCP server connections' },
  agent_prompts: { displayName: 'Agent Prompts', description: 'System prompts for agents' },
  embeddings: { displayName: 'Embeddings', description: 'Embedding model config' },
};

/**
 * Dynamically discover all top-level section keys from settings
 */
export function getSectionKeys(): string[] {
  const settings = getRawSettings();
  if (!settings) return [];
  return Object.keys(settings);
}

/**
 * Get display info for a section - known sections have descriptions,
 * unknown sections use key name as display name
 */
export function getSectionInfo(key: string): SectionInfo {
  const known = KNOWN_SECTIONS[key];
  if (known) {
    return {
      key,
      displayName: known.displayName,
      description: known.description,
      hasValidator: hasValidator(key),
    };
  }
  // Unknown section - use key name, mark as custom
  return {
    key,
    displayName: key,
    description: 'Custom section',
    hasValidator: false,
  };
}

/**
 * Get all sections with their display info
 */
export function getAllSections(): SectionInfo[] {
  return getSectionKeys().map(getSectionInfo);
}

/**
 * Get a section's content as a YAML string
 */
export function getSectionAsYaml(key: string): string {
  const settings = getRawSettings();
  if (!settings || !(key in settings)) {
    return '';
  }
  const value = settings[key];
  // Convert to YAML with nice formatting
  return stringifyYaml(value, {
    indent: 2,
    lineWidth: 0, // Don't wrap lines
  }).trim();
}

/**
 * Validate a section's YAML content
 */
export function validateSectionYaml(key: string, yaml: string): ValidationResult {
  return validateSection(key, yaml);
}

/**
 * Update a section with new YAML content
 * Returns validation result - only saves if valid
 */
export function updateSection(key: string, yaml: string): ValidationResult {
  // First validate
  const result = validateSection(key, yaml);
  if (!result.isValid) {
    return result;
  }

  // Get current settings
  const settings = getRawSettings();
  if (!settings) {
    return {
      isValid: false,
      errors: [{ path: '', message: 'No settings file found' }],
    };
  }

  // Parse the new YAML value
  let newValue: unknown;
  try {
    newValue = parseYaml(yaml);
  } catch (error) {
    return {
      isValid: false,
      errors: [{ path: '', message: 'Failed to parse YAML' }],
    };
  }

  // Update the section
  settings[key] = newValue;

  // Save settings (with backup)
  try {
    saveSettings(settings);
    clearSettingsCache();
    return { isValid: true, errors: [], parsedValue: newValue };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to save settings';
    return {
      isValid: false,
      errors: [{ path: '', message }],
    };
  }
}

/**
 * Add a new section to settings
 */
export function addSection(key: string, yaml: string): ValidationResult {
  const settings = getRawSettings();
  if (!settings) {
    return {
      isValid: false,
      errors: [{ path: '', message: 'No settings file found' }],
    };
  }

  if (key in settings) {
    return {
      isValid: false,
      errors: [{ path: '', message: `Section '${key}' already exists` }],
    };
  }

  return updateSection(key, yaml);
}

/**
 * Delete a section from settings
 */
export function deleteSection(key: string): ValidationResult {
  const settings = getRawSettings();
  if (!settings) {
    return {
      isValid: false,
      errors: [{ path: '', message: 'No settings file found' }],
    };
  }

  if (!(key in settings)) {
    return {
      isValid: false,
      errors: [{ path: '', message: `Section '${key}' not found` }],
    };
  }

  delete settings[key];

  try {
    saveSettings(settings);
    clearSettingsCache();
    return { isValid: true, errors: [] };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to save settings';
    return {
      isValid: false,
      errors: [{ path: '', message }],
    };
  }
}

export { getSettingsPath };
