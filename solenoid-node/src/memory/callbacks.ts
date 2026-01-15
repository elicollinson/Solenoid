import type { AgentRequest } from '../agents/types.js';
import type { Message } from '../llm/types.js';
import { getMemoryService, type MemoryService } from './service.js';
import type { SearchResult } from './schema.js';

const DEFAULT_APP_NAME = 'solenoid';
const DEFAULT_USER_ID = 'default';

export function createMemoryCallbacks(memoryService?: MemoryService) {
  const getService = () => {
    if (memoryService) return memoryService;
    try {
      return getMemoryService();
    } catch {
      return null;
    }
  };

  const injectMemories = async (request: AgentRequest): Promise<AgentRequest> => {
    const service = getService();
    if (!service) return request;

    const userId = (request.context.state['userId'] as string) ?? DEFAULT_USER_ID;
    const appName = (request.context.state['appName'] as string) ?? DEFAULT_APP_NAME;
    const query = request.context.state['originalUserQuery'] as string;

    if (!query) return request;

    try {
      const results = await service.search(query, userId, appName);

      if (results.length > 0) {
        request.context.state['loadedMemories'] = results;

        const memoryContext = formatMemoriesForContext(results);
        request.context.state['memoryContext'] = memoryContext;
      }
    } catch (error) {
      console.warn('Memory injection failed:', error);
    }

    return request;
  };

  const saveMemories = async (
    request: AgentRequest,
    response: Message
  ): Promise<void> => {
    const service = getService();
    if (!service) return;

    const userId = (request.context.state['userId'] as string) ?? DEFAULT_USER_ID;
    const appName = (request.context.state['appName'] as string) ?? DEFAULT_APP_NAME;

    // Store the conversation exchange as an episodic memory
    const query = request.context.state['originalUserQuery'] as string;
    if (!query || !response.content) return;

    try {
      await service.addMemory({
        user_id: userId,
        app_name: appName,
        memory_type: 'episodic',
        text: `User asked: "${query.substring(0, 200)}". Assistant responded about: ${response.content.substring(0, 200)}`,
        importance: 2,
      });
    } catch (error) {
      console.warn('Memory storage failed:', error);
    }
  };

  return {
    injectMemories,
    saveMemories,
  };
}

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
