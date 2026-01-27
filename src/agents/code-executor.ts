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
import type { AppSettings } from '../config/index.js';
import { getAdkModelName, getAgentPrompt, loadSettings } from '../config/index.js';
import { saveMemoriesOnFinalResponse } from '../memory/callbacks.js';
import { executeCodeAdkTool } from '../tools/adk-tools.js';
import { executeCode } from '../tools/code-execution.js';

// Re-export executeCode for backward compatibility
export { executeCode };

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
let settings: AppSettings | null;
try {
  settings = loadSettings();
} catch {
  settings = null;
}

const modelName = settings ? getAdkModelName('code_executor_agent', settings) : 'gemini-2.5-flash';

const customPrompt = settings ? getAgentPrompt('code_executor_agent', settings) : undefined;

/**
 * Code Executor LlmAgent - Python execution specialist
 */
export const codeExecutorAgent = new LlmAgent({
  name: 'code_executor_agent',
  model: modelName,
  description:
    'Python code execution specialist for calculations, algorithms, and data processing.',
  instruction: customPrompt ?? DEFAULT_INSTRUCTION,
  tools: [executeCodeAdkTool],
  afterModelCallback: saveMemoriesOnFinalResponse,
});

// Factory function for backwards compatibility
export function createCodeExecutorAgent(): LlmAgent {
  return codeExecutorAgent;
}

// Legacy tool executors export for backwards compatibility
export const codeExecutorToolExecutors: Record<
  string,
  (args: Record<string, unknown>) => Promise<string>
> = {
  execute_code: async (args) => executeCode(args.code as string),
};
