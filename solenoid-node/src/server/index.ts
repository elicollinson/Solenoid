import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';
import { streamSSE } from 'hono/streaming';
import { zValidator } from '@hono/zod-validator';
import { z } from 'zod';
import { loadSettings } from '../config/index.js';
import { createAgentHierarchy, createAgentHierarchySync, type AgentRunner } from '../agents/index.js';

const app = new Hono();
let agentRunner: AgentRunner | null = null;
let initPromise: Promise<void> | null = null;

async function initializeRunner(): Promise<void> {
  if (agentRunner) return;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    try {
      const { runner } = await createAgentHierarchy();
      agentRunner = runner;
    } catch (error) {
      console.warn('Async agent initialization failed, falling back to sync:', error);
      const { runner } = createAgentHierarchySync();
      agentRunner = runner;
    }
  })();

  return initPromise;
}

function getAgentRunner(): AgentRunner {
  if (!agentRunner) {
    // Fallback to sync if called before async init completes
    const { runner } = createAgentHierarchySync();
    agentRunner = runner;
  }
  return agentRunner;
}

app.use('/*', cors());
app.use('/*', logger());

app.get('/health', (c) => {
  return c.json({
    status: 'healthy',
    version: '2.0.0-alpha.1',
    timestamp: new Date().toISOString(),
  });
});

app.get('/config', (c) => {
  try {
    const settings = loadSettings();
    return c.json({
      models: {
        default: settings.models.default.name,
        provider: settings.models.default.provider,
      },
      embeddings: {
        provider: settings.embeddings.provider,
        model: settings.embeddings.model,
      },
      mcp_servers: Object.keys(settings.mcp_servers),
    });
  } catch {
    return c.json({ error: 'Configuration not loaded' }, 500);
  }
});

const RunAgentInputSchema = z.object({
  thread_id: z.string().optional(),
  run_id: z.string().optional(),
  messages: z.array(
    z.object({
      role: z.enum(['user', 'assistant', 'system']),
      content: z.string(),
    })
  ),
});

app.post('/api/agent', zValidator('json', RunAgentInputSchema), async (c) => {
  const input = c.req.valid('json');
  const runId = input.run_id ?? crypto.randomUUID();
  const threadId = input.thread_id ?? crypto.randomUUID();

  const lastUserMessage = input.messages.findLast(
    (m: { role: string; content: string }) => m.role === 'user'
  );
  if (!lastUserMessage) {
    return c.json({ error: 'No user message provided' }, 400);
  }

  return streamSSE(c, async (stream) => {
    await stream.writeSSE({
      event: 'run_started',
      data: JSON.stringify({
        type: 'RUN_STARTED',
        run_id: runId,
        thread_id: threadId,
      }),
    });

    const messageId = crypto.randomUUID();
    let messageStarted = false;

    try {
      const runner = getAgentRunner();

      for await (const chunk of runner.run(lastUserMessage.content, threadId)) {
        if (chunk.type === 'text' && chunk.content) {
          if (!messageStarted) {
            await stream.writeSSE({
              event: 'text_message_start',
              data: JSON.stringify({
                type: 'TEXT_MESSAGE_START',
                message_id: messageId,
                role: 'assistant',
              }),
            });
            messageStarted = true;
          }

          await stream.writeSSE({
            event: 'text_message_content',
            data: JSON.stringify({
              type: 'TEXT_MESSAGE_CONTENT',
              delta: chunk.content,
            }),
          });
        }

        if (chunk.type === 'tool_call' && chunk.toolCall) {
          await stream.writeSSE({
            event: 'tool_call_start',
            data: JSON.stringify({
              type: 'TOOL_CALL_START',
              tool_call_id: crypto.randomUUID(),
              tool_name: chunk.toolCall.function.name,
            }),
          });
        }

        if (chunk.type === 'transfer' && chunk.transferTo) {
          await stream.writeSSE({
            event: 'agent_transfer',
            data: JSON.stringify({
              type: 'AGENT_TRANSFER',
              from_agent: 'current',
              to_agent: chunk.transferTo,
            }),
          });
        }
      }

      if (messageStarted) {
        await stream.writeSSE({
          event: 'text_message_end',
          data: JSON.stringify({
            type: 'TEXT_MESSAGE_END',
          }),
        });
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';

      if (!messageStarted) {
        await stream.writeSSE({
          event: 'text_message_start',
          data: JSON.stringify({
            type: 'TEXT_MESSAGE_START',
            message_id: messageId,
            role: 'assistant',
          }),
        });
      }

      await stream.writeSSE({
        event: 'text_message_content',
        data: JSON.stringify({
          type: 'TEXT_MESSAGE_CONTENT',
          delta: `Error: ${errorMessage}`,
        }),
      });

      await stream.writeSSE({
        event: 'text_message_end',
        data: JSON.stringify({
          type: 'TEXT_MESSAGE_END',
        }),
      });
    }

    await stream.writeSSE({
      event: 'run_finished',
      data: JSON.stringify({
        type: 'RUN_FINISHED',
        run_id: runId,
      }),
    });
  });
});

export function createServer() {
  return app;
}

export async function startServer(port: number = 8001) {
  console.log(`Starting Solenoid server on port ${port}...`);

  // Initialize agent runner (with MCP connections) before starting server
  await initializeRunner();

  const server = serve({
    fetch: app.fetch,
    port,
  });

  console.log(`Server running at http://localhost:${port}`);
  console.log(`Health check: http://localhost:${port}/health`);

  return server;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const port = parseInt(process.env['PORT'] ?? '8001', 10);
  startServer(port);
}

export default app;
