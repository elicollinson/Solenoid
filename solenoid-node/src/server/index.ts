/**
 * API Server
 *
 * HTTP server exposing the agent system via REST API with SSE streaming.
 * Provides endpoints for health checks, configuration, and agent interaction.
 * Streams agent responses in real-time using Server-Sent Events.
 *
 * AG-UI Protocol Compliance:
 * - Uses @ag-ui/core EventType enum for event types
 * - Streams events using AG-UI event encoder
 * - Includes tool call arguments for frontend rendering
 *
 * Endpoints:
 * - GET /health: Server health check
 * - GET /config: Current configuration summary
 * - POST /api/agent: Run agent with SSE streaming response
 *
 * Dependencies:
 * - hono: Lightweight web framework for edge/Node.js
 * - @hono/node-server: Node.js adapter for Hono
 * - @hono/zod-validator: Request validation using Zod schemas
 * - @ag-ui/core: AG-UI protocol event types
 */
import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';
import { streamSSE } from 'hono/streaming';
import { zValidator } from '@hono/zod-validator';
import { z } from 'zod';
import { setLogLevel, LogLevel } from '@google/adk';
import { loadSettings } from '../config/index.js';
import { createAgentHierarchy, createAgentHierarchySync, type AgentRunner } from '../agents/index.js';
import { serverLogger, setupErrorHandlers } from '../utils/logger.js';
import {
  EventType,
  createRunStartedEvent,
  createRunFinishedEvent,
  createTextMessageStartEvent,
  createTextMessageContentEvent,
  createTextMessageEndEvent,
  createToolCallStartEvent,
  createToolCallArgsEvent,
  createToolCallEndEvent,
  createCustomEvent,
} from '../ag-ui/index.js';

// Enable ADK debug logging
setLogLevel(LogLevel.DEBUG);

setupErrorHandlers(serverLogger);

const app = new Hono();
let agentRunner: AgentRunner | null = null;
let initPromise: Promise<void> | null = null;

async function initializeRunner(): Promise<void> {
  if (agentRunner) return;
  if (initPromise) return initPromise;

  serverLogger.info('Initializing agent runner');

  initPromise = (async () => {
    try {
      const { runner } = await createAgentHierarchy();
      agentRunner = runner;
      serverLogger.info('Agent hierarchy initialized (async)');
    } catch (error) {
      serverLogger.warn({ error }, 'Async agent initialization failed, falling back to sync');
      const { runner } = createAgentHierarchySync();
      agentRunner = runner;
      serverLogger.info('Agent hierarchy initialized (sync fallback)');
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

// Only use console logger if not in quiet mode (UI running)
if (!process.env['SOLENOID_QUIET']) {
  app.use('/*', logger());
}

// Always log requests to file
app.use('/*', async (c, next) => {
  const start = Date.now();
  await next();
  const ms = Date.now() - start;
  serverLogger.info({ method: c.req.method, path: c.req.path, status: c.res.status, ms }, 'request');
});

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
    // AG-UI: RUN_STARTED event
    await stream.writeSSE({
      event: EventType.RUN_STARTED.toLowerCase(),
      data: JSON.stringify(createRunStartedEvent(runId, threadId)),
    });

    const messageId = crypto.randomUUID();
    let messageStarted = false;

    try {
      const runner = getAgentRunner();

      for await (const chunk of runner.run(lastUserMessage.content, threadId)) {
        if (chunk.type === 'text' && chunk.content) {
          if (!messageStarted) {
            // AG-UI: TEXT_MESSAGE_START event
            await stream.writeSSE({
              event: EventType.TEXT_MESSAGE_START.toLowerCase(),
              data: JSON.stringify(createTextMessageStartEvent(messageId, 'assistant')),
            });
            messageStarted = true;
          }

          // AG-UI: TEXT_MESSAGE_CONTENT event
          await stream.writeSSE({
            event: EventType.TEXT_MESSAGE_CONTENT.toLowerCase(),
            data: JSON.stringify(createTextMessageContentEvent(messageId, chunk.content)),
          });
        }

        if (chunk.type === 'tool_call' && chunk.toolCall) {
          const toolCallId = crypto.randomUUID();
          const toolArgs = chunk.toolCall.function.arguments;

          // AG-UI: TOOL_CALL_START event
          await stream.writeSSE({
            event: EventType.TOOL_CALL_START.toLowerCase(),
            data: JSON.stringify(createToolCallStartEvent(toolCallId, chunk.toolCall.function.name, messageId)),
          });

          // AG-UI: TOOL_CALL_ARGS event - stream the full arguments
          if (toolArgs) {
            const argsStr = typeof toolArgs === 'string' ? toolArgs : JSON.stringify(toolArgs);
            await stream.writeSSE({
              event: EventType.TOOL_CALL_ARGS.toLowerCase(),
              data: JSON.stringify(createToolCallArgsEvent(toolCallId, argsStr)),
            });
          }

          // AG-UI: TOOL_CALL_END event
          await stream.writeSSE({
            event: EventType.TOOL_CALL_END.toLowerCase(),
            data: JSON.stringify(createToolCallEndEvent(toolCallId)),
          });
        }

        if (chunk.type === 'transfer' && chunk.transferTo) {
          // AG-UI: CUSTOM event for agent transfer
          await stream.writeSSE({
            event: EventType.CUSTOM.toLowerCase(),
            data: JSON.stringify(createCustomEvent('agent_transfer', {
              from_agent: 'current',
              to_agent: chunk.transferTo,
            })),
          });
        }
      }

      if (messageStarted) {
        // AG-UI: TEXT_MESSAGE_END event
        await stream.writeSSE({
          event: EventType.TEXT_MESSAGE_END.toLowerCase(),
          data: JSON.stringify(createTextMessageEndEvent(messageId)),
        });
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';

      if (!messageStarted) {
        await stream.writeSSE({
          event: EventType.TEXT_MESSAGE_START.toLowerCase(),
          data: JSON.stringify(createTextMessageStartEvent(messageId, 'assistant')),
        });
      }

      await stream.writeSSE({
        event: EventType.TEXT_MESSAGE_CONTENT.toLowerCase(),
        data: JSON.stringify(createTextMessageContentEvent(messageId, `Error: ${errorMessage}`)),
      });

      await stream.writeSSE({
        event: EventType.TEXT_MESSAGE_END.toLowerCase(),
        data: JSON.stringify(createTextMessageEndEvent(messageId)),
      });
    }

    // AG-UI: RUN_FINISHED event
    await stream.writeSSE({
      event: EventType.RUN_FINISHED.toLowerCase(),
      data: JSON.stringify(createRunFinishedEvent(runId)),
    });
  });
});

export function createServer() {
  return app;
}

export async function startServer(port: number = 8001) {
  serverLogger.info({ port }, 'Starting Solenoid server');

  // Initialize agent runner (with MCP connections) before starting server
  await initializeRunner();

  const server = serve({
    fetch: app.fetch,
    port,
  });

  serverLogger.info({ port, url: `http://localhost:${port}` }, 'Server started');

  return server;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const port = parseInt(process.env['PORT'] ?? '8001', 10);
  startServer(port);
}

export default app;
