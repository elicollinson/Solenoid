/**
 * Python Sandbox (Pyodide Engine)
 *
 * Secure Python execution environment using WebAssembly. Runs Python code
 * in an isolated sandbox with captured stdout/stderr and virtual filesystem
 * for file I/O. Preloads micropip and pygal for package management and charting.
 *
 * Dependencies:
 * - pyodide: CPython compiled to WebAssembly for in-browser/in-Node Python
 *   - micropip: Package installer for pure-Python wheels
 *   - pygal: SVG charting library (pre-installed)
 */
import type { PyodideInterface } from 'pyodide';
import { agentLogger } from '../utils/logger.js';

export interface ExecutionResult {
  stdout: string;
  stderr: string;
  outcome: 'success' | 'error';
  outputFiles: Record<string, string>;
}

export class PythonSandbox {
  private pyodide: PyodideInterface | null = null;
  private initialized = false;

  async initialize(): Promise<void> {
    if (this.initialized) return;

    try {
      const { loadPyodide } = await import('pyodide');
      this.pyodide = await loadPyodide({
        stdout: () => {},
        stderr: () => {},
      });

      // Install commonly used packages
      await this.pyodide.loadPackage(['micropip']);
      const micropip = this.pyodide.pyimport('micropip');

      try {
        await micropip.install('pygal');
      } catch {
        agentLogger.warn('Sandbox: Failed to install pygal');
      }

      this.initialized = true;
      agentLogger.info('Sandbox: Pyodide initialized');
    } catch (error) {
      agentLogger.warn({ error }, 'Sandbox: Pyodide not available');
      this.initialized = true; // Mark as initialized to prevent retry
    }
  }

  async run(
    code: string,
    contextFiles?: Record<string, string>
  ): Promise<ExecutionResult> {
    if (!this.pyodide) {
      return {
        stdout: '',
        stderr: 'Python sandbox not available. Pyodide failed to initialize.',
        outcome: 'error',
        outputFiles: {},
      };
    }

    let stdout = '';
    let stderr = '';

    // Set up stdout/stderr capture
    this.pyodide.setStdout({
      batched: (text: string) => {
        stdout += text + '\n';
      },
    });

    this.pyodide.setStderr({
      batched: (text: string) => {
        stderr += text + '\n';
      },
    });

    // Write context files to virtual filesystem
    if (contextFiles) {
      for (const [name, content] of Object.entries(contextFiles)) {
        this.pyodide.FS.writeFile(name, content);
      }
    }

    try {
      await this.pyodide.runPythonAsync(code);

      const outputFiles = this.captureOutputFiles(contextFiles);

      return {
        stdout: stdout.trim(),
        stderr: stderr.trim(),
        outcome: 'success',
        outputFiles,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        stdout: stdout.trim(),
        stderr: stderr.trim() || errorMessage,
        outcome: 'error',
        outputFiles: {},
      };
    }
  }

  private captureOutputFiles(
    contextFiles?: Record<string, string>
  ): Record<string, string> {
    if (!this.pyodide) return {};

    const files: Record<string, string> = {};
    const contextFileNames = new Set(Object.keys(contextFiles ?? {}));

    try {
      const entries = this.pyodide.FS.readdir('.');
      for (const entry of entries) {
        if (entry === '.' || entry === '..') continue;
        if (contextFileNames.has(entry)) continue;

        try {
          const stat = this.pyodide.FS.stat(entry);
          if (this.pyodide.FS.isFile(stat.mode)) {
            const content = this.pyodide.FS.readFile(entry, { encoding: 'utf8' });
            files[entry] = content as string;
          }
        } catch {
          // Skip files we can't read
        }
      }
    } catch {
      // FS operations failed
    }

    return files;
  }

  isAvailable(): boolean {
    return this.pyodide !== null;
  }
}

let defaultSandbox: PythonSandbox | null = null;

export function getPythonSandbox(): PythonSandbox {
  if (!defaultSandbox) {
    defaultSandbox = new PythonSandbox();
  }
  return defaultSandbox;
}
