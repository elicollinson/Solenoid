import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';
import { streamSSE } from 'hono/streaming';
import { zValidator } from '@hono/zod-validator';
import { z } from 'zod';
import { loadSettings } from '../config/index.js';

const app = new Hono();

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
  } catch (error) {
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

  return streamSSE(c, async (stream) => {
    await stream.writeSSE({
      event: 'run_started',
      data: JSON.stringify({
        type: 'RUN_STARTED',
        run_id: runId,
        thread_id: threadId,
      }),
    });

    await stream.writeSSE({
      event: 'text_message_start',
      data: JSON.stringify({
        type: 'TEXT_MESSAGE_START',
        message_id: crypto.randomUUID(),
        role: 'assistant',
      }),
    });

    const placeholder = 'Agent system not yet implemented. This is a placeholder response.';
    for (const char of placeholder) {
      await stream.writeSSE({
        event: 'text_message_content',
        data: JSON.stringify({
          type: 'TEXT_MESSAGE_CONTENT',
          delta: char,
        }),
      });
      await new Promise((resolve) => setTimeout(resolve, 10));
    }

    await stream.writeSSE({
      event: 'text_message_end',
      data: JSON.stringify({
        type: 'TEXT_MESSAGE_END',
      }),
    });

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
