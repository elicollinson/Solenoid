/**
 * Web Reader Tool
 *
 * Fetches and extracts text content from web pages. Strips HTML tags,
 * decodes entities, and cleans whitespace. Truncates content to 10,000
 * characters to stay within LLM context limits.
 */
import type { ToolDefinition } from '../llm/types.js';

const MAX_CONTENT_LENGTH = 10000;

export async function readWebpage(url: string): Promise<string> {
  try {
    const response = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; Solenoid/2.0; +https://github.com/solenoid)',
      },
    });

    if (!response.ok) {
      return `Error reading ${url}: HTTP ${response.status}`;
    }

    const html = await response.text();
    const text = extractTextFromHtml(html);

    if (text.length > MAX_CONTENT_LENGTH) {
      return `${text.substring(0, MAX_CONTENT_LENGTH)}\n\n[Content truncated...]`;
    }

    return text;
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return `Error reading ${url}: ${message}`;
  }
}

function extractTextFromHtml(html: string): string {
  // Remove script and style tags with their content
  let text = html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
  text = text.replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '');

  // Remove all HTML tags
  text = text.replace(/<[^>]+>/g, ' ');

  // Decode common HTML entities
  text = text
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&mdash;/g, '—')
    .replace(/&ndash;/g, '–');

  // Clean up whitespace
  text = text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .join('\n');

  // Collapse multiple spaces
  text = text.replace(/ {2,}/g, ' ');

  return text.trim();
}

export const readWebpageToolDef: ToolDefinition = {
  type: 'function',
  function: {
    name: 'read_webpage',
    description:
      'Reads the content of a web page and returns the text. Use this to get detailed information from a specific URL.',
    parameters: {
      type: 'object',
      properties: {
        url: {
          type: 'string',
          description: 'The URL of the web page to read',
        },
      },
      required: ['url'],
    },
  },
};
