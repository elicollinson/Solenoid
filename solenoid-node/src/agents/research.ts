/**
 * Research Agent (ADK)
 *
 * Web research specialist that gathers information from the internet.
 * Uses Brave Search API for discovery and fetches full page content
 * for detailed analysis. Produces structured research reports with
 * source citations.
 *
 * Tools:
 * - universal_search: Brave Search API for web queries
 * - read_webpage: Fetches and extracts text from URLs
 *
 * Dependencies:
 * - @google/adk: LlmAgent for ADK-compatible agent
 */
import { LlmAgent } from '@google/adk';
import { getAgentPrompt, loadSettings, getAdkModelName } from '../config/index.js';
import { braveSearchAdkTool, readWebpageAdkTool } from '../tools/adk-tools.js';
import { saveMemoriesOnFinalResponse } from '../memory/callbacks.js';

const DEFAULT_INSTRUCTION = `You are the Research Specialist, an expert in gathering comprehensive information from the web.

### ROLE
You perform deep, thorough research on topics using web search and page retrieval.

### AVAILABLE TOOLS
- universal_search: Web search (returns titles, URLs, snippets). Use for finding initial sources.
- read_webpage: Fetch full page content. Use for getting detailed information from a specific URL.

### RESEARCH METHODOLOGY

1. **SEARCH BROADLY**
   - Start with universal_search using relevant keywords
   - Review the snippets to identify the most promising sources

2. **DIVE DEEP**
   - Use read_webpage on the 2-3 most relevant URLs
   - Extract key facts, data, and insights

3. **VERIFY & SYNTHESIZE**
   - Look for consensus across sources
   - Note any discrepancies or conflicting information

4. **REPORT FINDINGS**
   - Provide a comprehensive summary
   - Cite sources with URLs
   - Highlight key facts and important details

### OUTPUT FORMAT

Structure your research report as:
## Summary
[Brief overview of findings]

## Key Findings
- [Finding 1]
- [Finding 2]

## Sources
- [Source 1 title](URL)
- [Source 2 title](URL)

### CONSTRAINTS
- NEVER fabricate information or URLs.
- NEVER present speculation as fact.
- ALWAYS cite sources for factual claims.
- Maximum 5 page reads per research task.`;

// Load settings with fallback
let settings;
try {
  settings = loadSettings();
} catch {
  settings = null;
}

const modelName = settings
  ? getAdkModelName('research_agent', settings)
  : 'gemini-2.5-flash';

const customPrompt = settings ? getAgentPrompt('research_agent', settings) : undefined;

/**
 * Research LlmAgent - web research specialist with search and web reading tools
 */
export const researchAgent = new LlmAgent({
  name: 'research_agent',
  model: modelName,
  description: 'Web research specialist that gathers information from the internet using search and page reading.',
  instruction: customPrompt ?? DEFAULT_INSTRUCTION,
  tools: [braveSearchAdkTool, readWebpageAdkTool],
  afterModelCallback: saveMemoriesOnFinalResponse,
});

// // Legacy tool executors export for backwards compatibility
// export const researchToolExecutors: Record<string, (args: Record<string, unknown>) => Promise<string>> = {
//   universal_search: async (args) => {
//     const { braveSearch } = await import('../tools/brave-search.js');
//     return braveSearch(args['query'] as string);
//   },
//   read_webpage: async (args) => {
//     const { readWebpage } = await import('../tools/web-reader.js');
//     return readWebpage(args['url'] as string);
//   },
// };
