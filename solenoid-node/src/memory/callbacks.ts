/**
 * Memory Callbacks for ADK Agents
 *
 * Agent lifecycle callbacks for memory integration with Google ADK LlmAgents.
 * Injects relevant memories into agent context before model calls and saves
 * conversation exchanges as episodic memories after responses.
 *
 * Dependencies:
 * - @google/adk: CallbackContext, LlmRequest, LlmResponse for callback types
 */
import type { CallbackContext, LlmRequest, LlmResponse } from '@google/adk';
import { getMemoryService, type MemoryService } from './service.js';
import type { SearchResult } from './schema.js';

const DEFAULT_APP_NAME = 'solenoid';
const DEFAULT_USER_ID = 'default';

/**
 * Gets the memory service, returning null if unavailable
 */
function getService(memoryService?: MemoryService): MemoryService | null {
  if (memoryService) return memoryService;
  try {
    return getMemoryService();
  } catch {
    return null;
  }
}

/**
 * Formats memory search results for injection into agent context
 */
function formatMemoriesForContext(results: SearchResult[]): string {
  if (results.length === 0) return '';

  const lines = results.map((r, i) => {
    const type = r.memory.memory_type;
    return `[${i + 1}] (${type}) ${r.text}`;
  });

  return `
## Relevant Memories
${lines.join('\n')}
`;
}

/**
 * ADK beforeModelCallback that injects relevant memories into the context
 */
export function createInjectMemoriesCallback(memoryService?: MemoryService) {
  return async ({ context }: { context: CallbackContext; request: LlmRequest }) => {
    const service = getService(memoryService);
    if (!service) return undefined;

    const state = context.state;
    const userId = (state.get('userId') as string) ?? DEFAULT_USER_ID;
    const appName = (state.get('appName') as string) ?? DEFAULT_APP_NAME;
    const query = state.get('originalUserQuery') as string;

    if (!query) return undefined;

    try {
      const results = await service.search(query, userId, appName);

      if (results.length > 0) {
        state.set('loadedMemories', results);
        const memoryContext = formatMemoriesForContext(results);
        state.set('memoryContext', memoryContext);
      }
    } catch (error) {
      console.warn('Memory injection failed:', error);
    }

    return undefined; // Continue to model
  };
}

/**
 * ADK afterModelCallback that saves conversation exchanges as episodic memories
 */
export function createSaveMemoriesCallback(memoryService?: MemoryService) {
  return async ({ context, response }: { context: CallbackContext; response: LlmResponse }) => {
    const service = getService(memoryService);
    if (!service) return undefined;

    const state = context.state;
    const userId = (state.get('userId') as string) ?? DEFAULT_USER_ID;
    const appName = (state.get('appName') as string) ?? DEFAULT_APP_NAME;
    const query = state.get('originalUserQuery') as string;

    // Extract text content from response
    const responseText = response.content?.parts
      ?.map((p) => p.text)
      .filter(Boolean)
      .join('');

    if (!query || !responseText) return undefined;

    try {
      await service.addMemory({
        user_id: userId,
        app_name: appName,
        memory_type: 'episodic',
        text: `User asked: "${query.substring(0, 200)}". Assistant responded about: ${responseText.substring(0, 200)}`,
        importance: 2,
      });
    } catch (error) {
      console.warn('Memory storage failed:', error);
    }

    return undefined; // Use original response
  };
}

/**
 * Pre-configured memory injection callback using default service
 */
export const injectMemories = createInjectMemoriesCallback();

/**
 * Pre-configured memory save callback using default service
 */
export const saveMemoriesOnFinalResponse = createSaveMemoriesCallback();
