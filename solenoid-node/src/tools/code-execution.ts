/**
 * Code Execution Utilities
 *
 * Python code execution in a secure WASM sandbox. Used by both the
 * code executor agent and the ADK tools.
 *
 * Dependencies:
 * - pyodide: WebAssembly Python runtime for secure sandboxed execution
 */
import { getPythonSandbox, type ExecutionResult } from '../sandbox/index.js';

/**
 * Execute Python code in the WASM sandbox
 * @param code Python code to execute
 * @returns Formatted execution result
 */
export async function executeCode(code: string): Promise<string> {
  const sandbox = getPythonSandbox();

  if (!sandbox.isAvailable()) {
    await sandbox.initialize();
  }

  const result = await sandbox.run(code);

  return formatExecutionResult(result);
}

/**
 * Format execution result for display
 */
function formatExecutionResult(result: ExecutionResult): string {
  const parts: string[] = [];

  parts.push(`## Execution ${result.outcome === 'success' ? 'Succeeded' : 'Failed'}`);

  if (result.stdout) {
    parts.push('\n### Output\n```\n' + result.stdout + '\n```');
  }

  if (result.stderr) {
    parts.push('\n### Errors\n```\n' + result.stderr + '\n```');
  }

  const fileNames = Object.keys(result.outputFiles);
  if (fileNames.length > 0) {
    parts.push('\n### Generated Files');
    for (const name of fileNames) {
      const content = result.outputFiles[name]!;
      const preview = content.length > 500 ? content.substring(0, 500) + '...' : content;
      parts.push(`\n**${name}**\n\`\`\`\n${preview}\n\`\`\``);
    }
  }

  return parts.join('\n');
}
