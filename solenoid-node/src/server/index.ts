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
import { setLogLevel, LogLevel, InMemoryRunner } from '@google/adk';
import { loadSettings } from '../config/index.js';
import { createAdkAgentHierarchy, createUserContent } from '../agents/index.js';
import { serverLogger, setupErrorHandlers } from '../utils/logger.js';
import {
  EventType,
  createRunStartedEvent,
  createRunFinishedEvent,
  createTextMessageStartEvent,
  createTextMessageContentEvent,
  createTextMessageEndEvent,
} from '../ag-ui/index.js';

// Enable ADK debug logging
setLogLevel(LogLevel.DEBUG);

setupErrorHandlers(serverLogger);

const app = new Hono();
let agentRunner: InMemoryRunner | null = null;

async function initializeRunner(): Promise<void> {
  if (agentRunner) return;

  serverLogger.info('Initializing agent runner');
  const { runner } = await createAdkAgentHierarchy();
  agentRunner = runner;
  serverLogger.info('Agent hierarchy initialized');
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
  const sessionId = input.thread_id ?? crypto.randomUUID();

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
      data: JSON.stringify(createRunStartedEvent(runId, sessionId)),
    });

    const messageId = crypto.randomUUID();
    let messageStarted = false;

    try {
      if (!agentRunner) {
        throw new Error('Agent runner not initialized');
      }

      // Ensure session exists (create if new)
      let session = await agentRunner.sessionService.getSession({
        appName: 'Solenoid',
        userId: 'user',
        sessionId: sessionId,
      });
      if (!session) {
        session = await agentRunner.sessionService.createSession({
          appName: 'Solenoid',
          userId: 'user',
          sessionId: sessionId,
        });
      }

      const message = createUserContent(lastUserMessage.content);

      for await (const chunk of agentRunner.runAsync({userId: "user", sessionId: sessionId, newMessage: message})) {
        serverLogger.info(chunk);

        // Extract text content from ADK event parts
        if (chunk.content?.parts) {
          for (const part of chunk.content.parts) {
            // Handle text content
            if ('text' in part && part.text) {
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
                data: JSON.stringify(createTextMessageContentEvent(messageId, part.text)),
              });
            }
          }
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
