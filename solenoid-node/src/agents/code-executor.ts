import { BaseAgent } from './base-agent.js';
import type { Agent } from './types.js';
import { getAgentPrompt, getModelConfig, loadSettings } from '../config/index.js';
import { getPythonSandbox, type ExecutionResult } from '../sandbox/index.js';
import type { ToolDefinition } from '../llm/types.js';

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

const executeCodeToolDef: ToolDefinition = {
  type: 'function',
  function: {
    name: 'execute_code',
    description: 'Execute Python code in a secure WASM sandbox. Returns stdout, stderr, and any generated files.',
    parameters: {
      type: 'object',
      properties: {
        code: {
          type: 'string',
          description: 'The Python code to execute. Use print() for output.',
        },
      },
      required: ['code'],
    },
  },
};

export async function executeCode(code: string): Promise<string> {
  const sandbox = getPythonSandbox();

  if (!sandbox.isAvailable()) {
    await sandbox.initialize();
  }

  const result = await sandbox.run(code);

  return formatExecutionResult(result);
}

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

export function createCodeExecutorAgent(): Agent {
  let settings;
  try {
    settings = loadSettings();
  } catch {
    settings = null;
  }

  const modelConfig = settings
    ? getModelConfig('code_executor_agent', settings)
    : { name: 'llama3.1:8b', provider: 'ollama_chat' as const, context_length: 128000 };

  const customPrompt = settings
    ? getAgentPrompt('code_executor_agent', settings)
    : undefined;

  return new BaseAgent({
    name: 'code_executor_agent',
    model: modelConfig.name,
    instruction: customPrompt ?? DEFAULT_INSTRUCTION,
    tools: [executeCodeToolDef],
    disallowTransferToParent: true,
  });
}

export const codeExecutorToolExecutors: Record<
  string,
  (args: Record<string, unknown>) => Promise<string>
> = {
  execute_code: async (args) => executeCode(args['code'] as string),
};
