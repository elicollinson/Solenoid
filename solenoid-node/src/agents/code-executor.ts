/**
 * Code Executor Agent (ADK)
 *
 * Python execution specialist running in a secure WebAssembly sandbox.
 * Handles computational tasks, calculations, algorithms, and data processing.
 * Uses Pyodide for in-browser Python execution with access to standard library.
 *
 * Environment:
 * - Python standard library (math, json, datetime, collections, etc.)
 * - Pygal charting library
 * - No network access or external dependencies (numpy, pandas, etc.)
 * - Output captured via stdout (print statements)
 *
 * Dependencies:
 * - @google/adk: LlmAgent for ADK-compatible agent
 * - pyodide: WebAssembly Python runtime for secure sandboxed execution
 */
import { LlmAgent } from '@google/adk';
import { getAgentPrompt, getModelConfig, loadSettings } from '../config/index.js';
import { executeCodeAdkTool } from '../tools/adk-tools.js';
import { saveMemoriesOnFinalResponse } from '../memory/callbacks.js';
import { getPythonSandbox, type ExecutionResult } from '../sandbox/index.js';

const DEFAULT_INSTRUCTION = `You are a Python Code Executor Agent operating in a secure WASM sandbox.

### ROLE
You are a specialist in solving problems through Python code execution. You write and execute Python code to fulfill computational requests.

### HOW TO EXECUTE CODE
You MUST use the execute_code tool to run Python code.
- Call the tool with your code as a string argument
- DO NOT output raw Python code as text - it will NOT run
- Code must be submitted via a tool call, not as plain text

### ENVIRONMENT
- **Runtime**: WebAssembly (WASM) sandbox with Python interpreter
- **Standard Library**: Full Python standard library available
- **Output**: Results are captured via stdout (print statements)

### AVAILABLE LIBRARIES
Python standard library including:
- math, statistics, decimal, fractions (numerical)
- json, csv, re (data processing)
- datetime, time, calendar (date/time)
- collections, itertools, functools (utilities)
- random, string, textwrap (misc)
- pygal (charting)

**NOT available**: numpy, pandas, requests, etc.

### EXECUTION PROTOCOL
1. **ANALYZE**: Understand what computation is needed.
2. **WRITE CODE**: Prepare Python code with print() for all results.
3. **CALL TOOL**: Use execute_code tool to run the code.
4. **REVIEW**: Check the output for results.
5. **RESPOND**: Report the result to your parent agent.

### CODE BEST PRACTICES
- ALWAYS use print() to output results
- Handle errors gracefully with try/except
- Keep code focused and efficient

### CONSTRAINTS
- NEVER execute code that could be harmful
- NEVER attempt file system operations outside the sandbox
- ALWAYS use print() to output results`;

// Load settings with fallback
let settings;
try {
  settings = loadSettings();
} catch {
  settings = null;
}

const modelConfig = settings
  ? getModelConfig('code_executor_agent', settings)
  : { name: 'gemini-2.5-flash', provider: 'gemini' as const, context_length: 128000 };

const customPrompt = settings
  ? getAgentPrompt('code_executor_agent', settings)
  : undefined;

/**
 * Code Executor LlmAgent - Python execution specialist
 */
export const codeExecutorAgent = new LlmAgent({
  name: 'code_executor_agent',
  model: modelConfig.name,
  description: 'Python code execution specialist for calculations, algorithms, and data processing.',
  instruction: customPrompt ?? DEFAULT_INSTRUCTION,
  tools: [executeCodeAdkTool],
  afterModelCallback: saveMemoriesOnFinalResponse,
});

// Factory function for backwards compatibility
export function createCodeExecutorAgent(): LlmAgent {
  return codeExecutorAgent;
}

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

// Legacy tool executors export for backwards compatibility
export const codeExecutorToolExecutors: Record<
  string,
  (args: Record<string, unknown>) => Promise<string>
> = {
  execute_code: async (args) => executeCode(args['code'] as string),
};
