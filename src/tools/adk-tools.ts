/**
 * ADK FunctionTool Wrappers
 *
 * Converts existing tool implementations to Google ADK FunctionTool pattern
 * with Zod schema validation. These tools are used by LlmAgents in the
 * ADK-based agent hierarchy.
 *
 * Tools:
 * - braveSearchAdkTool: Web search using Brave Search API
 * - readWebpageAdkTool: Fetch and extract text from URLs
 * - executeCodeAdkTool: Execute Python code in WASM sandbox
 * - generateChartAdkTool: Generate Pygal charts in WASM sandbox
 */
import { FunctionTool } from '@google/adk';
import { z } from 'zod';
import { braveSearch } from './brave-search.js';
import { executeCode } from './code-execution.js';
import { readWebpage } from './web-reader.js';

/**
 * Brave Search ADK Tool
 * Performs web searches using the Brave Search API.
 */
export const braveSearchAdkTool = new FunctionTool({
  name: 'universal_search',
  description: 'Performs a web search using Brave Search. Returns titles, links, and snippets.',
  parameters: z.object({
    query: z.string().describe('The search query string'),
  }),
  execute: async ({ query }) => {
    const result = await braveSearch(query);
    return { result };
  },
});

/**
 * Web Reader ADK Tool
 * Fetches and extracts text content from web pages.
 */
export const readWebpageAdkTool = new FunctionTool({
  name: 'read_webpage',
  description:
    'Reads the content of a web page and returns the text. Use this to get detailed information from a specific URL.',
  parameters: z.object({
    url: z.string().describe('The URL of the web page to read'),
  }),
  execute: async ({ url }) => {
    const result = await readWebpage(url);
    return { result };
  },
});

/**
 * Code Executor ADK Tool
 * Executes Python code in a secure WASM sandbox.
 */
export const executeCodeAdkTool = new FunctionTool({
  name: 'execute_code',
  description:
    'Execute Python code in a secure WASM sandbox. Returns stdout, stderr, and any generated files.',
  parameters: z.object({
    code: z.string().describe('The Python code to execute. Use print() for output.'),
  }),
  execute: async ({ code }) => {
    const result = await executeCode(code);
    return { result };
  },
});

/**
 * Chart Generator ADK Tool
 * Generates charts using Pygal in a WASM sandbox.
 */
export const generateChartAdkTool = new FunctionTool({
  name: 'generate_chart',
  description:
    'Generate a chart using Pygal. The code should create a chart and save it to chart.svg.',
  parameters: z.object({
    code: z
      .string()
      .describe('Python code using Pygal to generate a chart. Must save to chart.svg.'),
  }),
  execute: async ({ code }) => {
    const result = await executeCode(code);
    return { result };
  },
});
