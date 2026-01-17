/**
 * Brave Search Tool
 *
 * Web search integration using the Brave Search API. Returns titles, URLs,
 * and snippets for search queries. API key can be set via environment variable
 * (BRAVE_SEARCH_API_KEY) or in app_settings.yaml.
 */
import { loadSettings } from '../config/index.js';
import type { ToolDefinition } from '../llm/types.js';

export async function braveSearch(query: string): Promise<string> {
  const apiKey = getApiKey();
  if (!apiKey) {
    return 'Error: BRAVE_SEARCH_API_KEY not found in environment variables or app_settings.yaml.';
  }

  const url = new URL('https://api.search.brave.com/res/v1/web/search');
  url.searchParams.set('q', query);
  url.searchParams.set('count', '10');

  try {
    const response = await fetch(url.toString(), {
      headers: {
        Accept: 'application/json',
        'Accept-Encoding': 'gzip',
        'X-Subscription-Token': apiKey,
      },
    });

    if (!response.ok) {
      return `Error: Search API returned ${response.status}`;
    }

    const data = (await response.json()) as {
      web?: { results?: Array<{ title?: string; url?: string; description?: string }> };
    };
    const results = data.web?.results ?? [];

    if (results.length === 0) {
      return 'No results found.';
    }

    const summary = results.map((result, i) => {
      const title = result.title ?? 'No Title';
      const link = result.url ?? '';
      const description = result.description ?? '';

      return `${i + 1}. ${title}\n   Link: ${link}\n   Snippet: ${description}`;
    });

    return summary.join('\n\n');
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return `Error performing search: ${message}`;
  }
}

function getApiKey(): string | undefined {
  const envKey = process.env['BRAVE_SEARCH_API_KEY'];
  if (envKey) return envKey;

  try {
    const settings = loadSettings();
    return settings.search.brave_search_api_key;
  } catch {
    return undefined;
  }
}

export const braveSearchToolDef: ToolDefinition = {
  type: 'function',
  function: {
    name: 'universal_search',
    description:
      'Performs a web search using Brave Search. Returns titles, links, and snippets.',
    parameters: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'The search query string',
        },
      },
      required: ['query'],
    },
  },
};
