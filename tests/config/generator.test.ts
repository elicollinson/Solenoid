import { describe, it, expect, beforeEach, afterEach } from 'bun:test';
import { existsSync, unlinkSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse as parseYaml } from 'yaml';
import {
  generateSettings,
  writeSettingsFile,
  getEnvVarStatus,
  getDefaultSettings,
  DEFAULT_ENV_MAPPINGS,
} from '../../src/config/generator.js';

describe('Config Generator', () => {
  const testOutputPath = resolve(process.cwd(), '.test-settings.yaml');

  // Store original env vars
  const originalEnv: Record<string, string | undefined> = {};

  beforeEach(() => {
    // Save and clear env vars
    originalEnv['BRAVE_SEARCH_API_KEY'] = process.env['BRAVE_SEARCH_API_KEY'];
    originalEnv['GOOGLE_API_KEY'] = process.env['GOOGLE_API_KEY'];
    originalEnv['GOOGLE_CX'] = process.env['GOOGLE_CX'];
    originalEnv['OLLAMA_HOST'] = process.env['OLLAMA_HOST'];
    originalEnv['MY_CUSTOM_KEY'] = process.env['MY_CUSTOM_KEY'];

    delete process.env['BRAVE_SEARCH_API_KEY'];
    delete process.env['GOOGLE_API_KEY'];
    delete process.env['GOOGLE_CX'];
    delete process.env['OLLAMA_HOST'];
    delete process.env['MY_CUSTOM_KEY'];
  });

  // Clean up test file after each test
  afterEach(() => {
    if (existsSync(testOutputPath)) {
      unlinkSync(testOutputPath);
    }
    // Restore original environment variables
    for (const [key, value] of Object.entries(originalEnv)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  });

  describe('getDefaultSettings', () => {
    it('should return valid default settings structure', () => {
      const settings = getDefaultSettings();

      expect(settings).toHaveProperty('embeddings');
      expect(settings).toHaveProperty('models');
      expect(settings).toHaveProperty('search');
      expect(settings).toHaveProperty('mcp_servers');
      expect(settings).toHaveProperty('agent_prompts');
    });

    it('should have correct default model config', () => {
      const settings = getDefaultSettings();

      expect(settings.models.default.provider).toBe('ollama_chat');
      expect(settings.models.default.context_length).toBe(128000);
    });

    it('should have correct default search config', () => {
      const settings = getDefaultSettings();

      expect(settings.search.provider).toBe('brave');
      expect(settings.search.brave_search_api_key).toBe('');
    });
  });

  describe('getEnvVarStatus', () => {
    it('should return status of all default env vars', () => {
      const status = getEnvVarStatus();

      expect(status).toHaveProperty('BRAVE_SEARCH_API_KEY');
      expect(status).toHaveProperty('GOOGLE_API_KEY');
      expect(status).toHaveProperty('GOOGLE_CX');
      expect(status).toHaveProperty('OLLAMA_HOST');
    });

    it('should detect when env var is set', () => {
      process.env['BRAVE_SEARCH_API_KEY'] = 'test-key-123';

      const status = getEnvVarStatus();

      expect(status['BRAVE_SEARCH_API_KEY']).toBe(true);
    });

    it('should detect when env var is not set', () => {
      // Ensure env var is not set
      delete process.env['BRAVE_SEARCH_API_KEY'];

      const status = getEnvVarStatus();

      expect(status['BRAVE_SEARCH_API_KEY']).toBe(false);
    });

    it('should treat empty string as not set', () => {
      process.env['BRAVE_SEARCH_API_KEY'] = '';

      const status = getEnvVarStatus();

      expect(status['BRAVE_SEARCH_API_KEY']).toBe(false);
    });
  });

  describe('generateSettings', () => {
    it('should generate default settings when no env vars are set', () => {
      const settings = generateSettings();

      expect(settings.search.brave_search_api_key).toBe('');
      expect(settings.embeddings.host).toBe('http://localhost:11434');
    });

    it('should inject BRAVE_SEARCH_API_KEY from env', () => {
      process.env['BRAVE_SEARCH_API_KEY'] = 'my-brave-api-key';

      const settings = generateSettings();

      expect(settings.search.brave_search_api_key).toBe('my-brave-api-key');
    });

    it('should inject OLLAMA_HOST from env', () => {
      process.env['OLLAMA_HOST'] = 'http://custom-ollama:11434';

      const settings = generateSettings();

      expect(settings.embeddings.host).toBe('http://custom-ollama:11434');
    });

    it('should inject multiple env vars', () => {
      process.env['BRAVE_SEARCH_API_KEY'] = 'brave-key';
      process.env['GOOGLE_API_KEY'] = 'google-key';
      process.env['GOOGLE_CX'] = 'google-cx-id';
      process.env['OLLAMA_HOST'] = 'http://remote:11434';

      const settings = generateSettings();

      expect(settings.search.brave_search_api_key).toBe('brave-key');
      expect(settings.search.google_api_key).toBe('google-key');
      expect(settings.search.google_cx).toBe('google-cx-id');
      expect(settings.embeddings.host).toBe('http://remote:11434');
    });

    it('should merge with baseSettings', () => {
      const baseSettings = {
        search: {
          provider: 'google' as const,
        },
      };

      process.env['GOOGLE_API_KEY'] = 'google-key';

      const settings = generateSettings({ baseSettings });

      // Provider should be from base settings
      expect(settings.search.provider).toBe('google');
      // API key should be from env
      expect(settings.search.google_api_key).toBe('google-key');
    });

    it('should support custom env mappings', () => {
      process.env['MY_CUSTOM_KEY'] = 'custom-value';

      const settings = generateSettings({
        envMappings: [{ envVar: 'MY_CUSTOM_KEY', settingsPath: ['search', 'brave_search_api_key'] }],
      });

      expect(settings.search.brave_search_api_key).toBe('custom-value');
    });

    it('should support additional env vars', () => {
      const settings = generateSettings({
        additionalEnvVars: {
          CUSTOM: { settingsPath: ['search', 'brave_search_api_key'], value: 'injected-value' },
        },
      });

      expect(settings.search.brave_search_api_key).toBe('injected-value');
    });

    it('should use onlySetEnvVars mode', () => {
      process.env['BRAVE_SEARCH_API_KEY'] = 'only-this';

      const settings = generateSettings({ onlySetEnvVars: true });

      // Only the env var that was set should be present
      expect(settings.search?.brave_search_api_key).toBe('only-this');
      // Other defaults should not be present (or undefined)
      expect(settings.models).toBeUndefined();
    });
  });

  describe('writeSettingsFile', () => {
    it('should write settings to file', () => {
      writeSettingsFile({ outputPath: testOutputPath });

      expect(existsSync(testOutputPath)).toBe(true);
    });

    it('should write valid YAML', () => {
      writeSettingsFile({ outputPath: testOutputPath });

      const content = readFileSync(testOutputPath, 'utf-8');
      const parsed = parseYaml(content);

      expect(parsed).toHaveProperty('embeddings');
      expect(parsed).toHaveProperty('models');
      expect(parsed).toHaveProperty('search');
    });

    it('should inject env vars into written file', () => {
      process.env['BRAVE_SEARCH_API_KEY'] = 'file-test-key';

      writeSettingsFile({ outputPath: testOutputPath });

      const content = readFileSync(testOutputPath, 'utf-8');
      const parsed = parseYaml(content) as { search: { brave_search_api_key: string } };

      expect(parsed.search.brave_search_api_key).toBe('file-test-key');
    });

    it('should return the path to the written file', () => {
      const path = writeSettingsFile({ outputPath: testOutputPath });

      expect(path).toBe(testOutputPath);
    });

    it('should not overwrite if overwrite is false and file exists', () => {
      // Write first time
      process.env['BRAVE_SEARCH_API_KEY'] = 'first-key';
      writeSettingsFile({ outputPath: testOutputPath });

      // Try to write again with different key
      process.env['BRAVE_SEARCH_API_KEY'] = 'second-key';
      writeSettingsFile({ outputPath: testOutputPath, overwrite: false });

      // Should still have first key
      const content = readFileSync(testOutputPath, 'utf-8');
      const parsed = parseYaml(content) as { search: { brave_search_api_key: string } };

      expect(parsed.search.brave_search_api_key).toBe('first-key');
    });

    it('should overwrite by default', () => {
      // Write first time
      process.env['BRAVE_SEARCH_API_KEY'] = 'first-key';
      writeSettingsFile({ outputPath: testOutputPath });

      // Write again with different key
      process.env['BRAVE_SEARCH_API_KEY'] = 'second-key';
      writeSettingsFile({ outputPath: testOutputPath });

      // Should have second key
      const content = readFileSync(testOutputPath, 'utf-8');
      const parsed = parseYaml(content) as { search: { brave_search_api_key: string } };

      expect(parsed.search.brave_search_api_key).toBe('second-key');
    });
  });

  describe('DEFAULT_ENV_MAPPINGS', () => {
    it('should have expected mappings', () => {
      const envVars = DEFAULT_ENV_MAPPINGS.map((m) => m.envVar);

      expect(envVars).toContain('BRAVE_SEARCH_API_KEY');
      expect(envVars).toContain('GOOGLE_API_KEY');
      expect(envVars).toContain('GOOGLE_CX');
      expect(envVars).toContain('OLLAMA_HOST');
    });

    it('should have valid settings paths', () => {
      for (const mapping of DEFAULT_ENV_MAPPINGS) {
        expect(Array.isArray(mapping.settingsPath)).toBe(true);
        expect(mapping.settingsPath.length).toBeGreaterThan(0);
      }
    });
  });
});
