/**
 * Settings manager for loading, validating, and saving application settings.
 *
 * This module provides a high-level interface for settings operations,
 * coordinating between the config loader and the validator.
 */

import { writeFileSync, existsSync, copyFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { stringify as stringifyYaml } from 'yaml';
import {
  validateSection,
  SECTION_INFO,
  type SectionInfo,
  type SectionKey,
  type ValidationResult,
} from './validator.js';
import { loadSettings, clearSettingsCache, findSettingsFile } from './settings.js';
import type { AppSettings } from './schema.js';

const DEFAULT_SETTINGS_FILENAME = 'app_settings.yaml';

/**
 * High-level manager for application settings.
 *
 * Provides methods to:
 * - Get current settings
 * - Get/update individual sections
 * - Validate changes before saving
 * - Persist changes to disk
 */
export class SettingsManager {
  private absolutePath: string;

  constructor(configPath: string = DEFAULT_SETTINGS_FILENAME) {
    // Try to find the settings file or use cwd
    const foundPath = findSettingsFile();
    this.absolutePath = foundPath ?? resolve(process.cwd(), configPath);
  }

  /**
   * Get the current settings, reloading from disk.
   */
  getSettings(): AppSettings {
    clearSettingsCache();
    return loadSettings(this.absolutePath);
  }

  /**
   * Get list of available section keys from current settings.
   */
  getSectionKeys(): SectionKey[] {
    const settings = this.getSettings();
    return Object.keys(settings) as SectionKey[];
  }

  /**
   * Get display information for a section.
   */
  getSectionInfo(key: SectionKey): SectionInfo {
    if (key in SECTION_INFO) {
      return SECTION_INFO[key];
    }
    // Generate default info for unknown sections
    return {
      key,
      displayName: key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      description: `Configure ${key} settings`,
    };
  }

  /**
   * Get info for all sections in current settings.
   */
  getAllSectionsInfo(): SectionInfo[] {
    return this.getSectionKeys().map((key) => this.getSectionInfo(key));
  }

  /**
   * Get a specific section's value.
   */
  getSection(key: SectionKey): AppSettings[SectionKey] {
    const settings = this.getSettings();
    return settings[key];
  }

  /**
   * Get a section's value formatted as YAML string.
   */
  getSectionAsYaml(key: SectionKey): string {
    const value = this.getSection(key);
    if (value === undefined || value === null) {
      return '';
    }
    return stringifyYaml(value, {
      indent: 2,
      lineWidth: 120,
    });
  }

  /**
   * Validate a section's YAML before saving.
   */
  validateSection(key: SectionKey, yamlString: string): ValidationResult {
    const referenceSettings = this.getSettings();
    return validateSection(key, yamlString, referenceSettings);
  }

  /**
   * Update a section with new YAML content.
   *
   * Validates the content before saving. If validation fails,
   * no changes are made to the settings file.
   */
  updateSection(key: SectionKey, yamlString: string): ValidationResult {
    // Validate first
    const result = this.validateSection(key, yamlString);
    if (!result.isValid) {
      return result;
    }

    // Load current settings, update section, and save
    try {
      const settings = this.getSettings();
      // Use type assertion for dynamic key assignment
      (settings as Record<string, unknown>)[key] = result.parsedValue;
      this.saveSettings(settings);

      // Clear cache so next load picks up changes
      clearSettingsCache();

      return result;
    } catch (error) {
      return {
        isValid: false,
        errors: [
          {
            path: '',
            message: `Failed to save: ${error instanceof Error ? error.message : 'Unknown error'}`,
          },
        ],
      };
    }
  }

  /**
   * Save settings dict to the YAML file.
   */
  private saveSettings(settings: AppSettings): void {
    // Create backup first
    const backupPath = this.absolutePath + '.bak';
    if (existsSync(this.absolutePath)) {
      copyFileSync(this.absolutePath, backupPath);
    }

    // Write new settings
    const yamlContent = stringifyYaml(settings, {
      indent: 2,
      lineWidth: 120,
    });
    writeFileSync(this.absolutePath, yamlContent, 'utf-8');
  }

  /**
   * Restore settings from the backup file.
   */
  restoreBackup(): boolean {
    const backupPath = this.absolutePath + '.bak';
    if (!existsSync(backupPath)) {
      return false;
    }

    copyFileSync(backupPath, this.absolutePath);
    clearSettingsCache();
    return true;
  }

  /**
   * Check if settings file exists.
   */
  settingsExist(): boolean {
    return existsSync(this.absolutePath);
  }

  /**
   * Get the absolute path to the settings file.
   */
  getSettingsPath(): string {
    return this.absolutePath;
  }
}

// Global singleton instance
let manager: SettingsManager | null = null;

/**
 * Get the global settings manager instance.
 */
export function getSettingsManager(): SettingsManager {
  if (!manager) {
    manager = new SettingsManager();
  }
  return manager;
}

/**
 * Reset the global settings manager (useful for testing).
 */
export function resetSettingsManager(): void {
  manager = null;
}
