# Solenoid: Python to TypeScript Conversion Plan

**Version:** 1.0
**Date:** January 2026
**Current Version:** 1.2.6 (Python)
**Target:** Full TypeScript implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Overview](#2-current-architecture-overview)
3. [Component-by-Component Conversion Plan](#3-component-by-component-conversion-plan)
4. [Dependency Mapping](#4-dependency-mapping)
5. [Architectural Changes](#5-architectural-changes)
6. [Performance Trade-offs](#6-performance-trade-offs)
7. [Risk Assessment](#7-risk-assessment)
8. [Migration Strategy](#8-migration-strategy)
9. [Testing Strategy](#9-testing-strategy)
10. [Appendix: Library API Comparisons](#10-appendix-library-api-comparisons)

---

## 1. Executive Summary

### Project Scope

Solenoid is a sophisticated multi-agent AI assistant with:
- 8 specialized agents in hierarchical delegation
- Terminal-based UI (TUI) with real-time streaming
- Local LLM inference via Ollama
- WASM-sandboxed Python code execution
- Hybrid semantic + keyword memory search
- MCP (Model Context Protocol) integration
- AG-UI protocol for frontend-backend communication

### Conversion Rationale

| Aspect | Python | TypeScript |
|--------|--------|------------|
| Runtime | CPython 3.11+ | Node.js 20+ / Bun |
| Type Safety | Runtime (Pydantic) | Compile-time + Runtime (Zod) |
| Concurrency | asyncio | Native async/await, Worker threads |
| Package Size | ~500MB (with ML deps) | ~50-100MB estimated |
| Startup Time | 3-5s (cold start) | <1s |
| Distribution | pip/pipx | npm/npx, single binary via pkg |

### Key Assumptions

1. **Google ADK TypeScript is used** - Official `@google/adk` package (released Dec 2025) provides API-compatible agent framework
2. **Ollama remains the LLM backend** - The Ollama JavaScript SDK is mature and feature-complete
3. **WASM Python execution continues** - Pyodide provides equivalent functionality in JS
4. **AG-UI protocol is maintained** - ADK TypeScript includes `@google/adk-devtools` for web UI
5. **MCP SDK available** - ADK has built-in MCP support via `McpToolset`
6. **Embedding models remain Ollama-based** - Alternatively, Transformers.js for local inference

### Critical Discovery: Google ADK TypeScript

Google released ADK for TypeScript (`@google/adk` v0.2.0) in December 2025. This is the **recommended approach** because:

- **API-compatible** with Python ADK - same concepts (Agent, subAgents, callbacks, tools)
- **Same agent hierarchy pattern** - `subAgents` property mirrors Python's `sub_agents`
- **Same callback system** - `beforeModelCallback`, `afterModelCallback`, `beforeToolCallback`
- **Built-in MCP support** - Same `McpToolset` pattern
- **Same runner pattern** - `InMemoryRunner` for session management
- **Built-in devtools** - `@google/adk-devtools` provides web UI

This dramatically simplifies the conversion - most agent code can be directly translated with minimal changes.

---

## 2. Current Architecture Overview

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Solenoid (Python)                           │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐    ┌──────────────────┐    ┌───────────────┐ │
│  │   Textual TUI    │◄──►│   FastAPI Server │◄──►│  Agent System │ │
│  │   (Frontend)     │    │   (AG-UI SSE)    │    │  (Google ADK) │ │
│  └──────────────────┘    └──────────────────┘    └───────────────┘ │
│           │                       │                      │         │
│           ▼                       ▼                      ▼         │
│  ┌──────────────────┐    ┌──────────────────┐    ┌───────────────┐ │
│  │   Chat Input     │    │   SSE Streaming  │    │   Memory      │ │
│  │   Message List   │    │   CORS Handling  │    │   (SQLite)    │ │
│  └──────────────────┘    └──────────────────┘    └───────────────┘ │
│                                                          │         │
│                                                          ▼         │
│  ┌──────────────────┐    ┌──────────────────┐    ┌───────────────┐ │
│  │   WASM Engine    │    │   MCP Toolsets   │    │   Embeddings  │ │
│  │   (wasmtime)     │    │   (stdio/http)   │    │   (Ollama)    │ │
│  └──────────────────┘    └──────────────────┘    └───────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Agent Hierarchy

```
user_proxy_agent (Entry Point)
    │
    ├── Memory Injection (before_model_callback)
    ├── Memory Storage (after_model_callback)
    │
    └── prime_agent (Router)
            │
            └── planning_agent (Coordinator)
                    │
                    ├── code_executor_agent (WASM Python)
                    ├── chart_generator_agent (Pygal + WASM)
                    ├── research_agent (Brave Search)
                    ├── mcp_agent (MCP Tools)
                    └── generic_executor_agent (Text/Knowledge)
```

### 2.3 Key Data Flows

1. **User Input → Agent Response**
   - TUI captures input → AG-UI POST → FastAPI → ADK Runner → Agent chain → SSE stream back

2. **Memory Retrieval**
   - Query → Ollama embedding → sqlite-vec KNN + FTS5 BM25 → RRF fusion → BGE rerank → Top-N

3. **Code Execution**
   - Agent generates code → WasmEngine → python.wasm sandbox → stdout/files capture

---

## 3. Component-by-Component Conversion Plan

### 3.1 Agent Framework

**Current:** Google ADK Python (`google-adk` v1.18.0)
**Target:** Google ADK TypeScript (`@google/adk` v0.2.0+)

#### Assumptions
- Google ADK TypeScript is API-compatible with the Python version
- `LlmAgent` class mirrors Python's `Agent` class
- Callbacks, tools, and sub-agents work identically
- `InMemoryRunner` provides session management

#### Architectural Changes

| Python (Google ADK) | TypeScript (Google ADK) |
|---------------------|-------------------------|
| `Agent(name, model, instruction, tools, sub_agents)` | `new LlmAgent({name, model, instruction, tools, subAgents})` |
| `sub_agents=[...]` | `subAgents: [...]` |
| `before_model_callback` | `beforeModelCallback` |
| `after_model_callback` | `afterModelCallback` |
| `before_tool_callback` | `beforeToolCallback` |
| `BaseMemoryService` | Custom memory service (same interface) |
| `disallow_transfer_to_parent=True` | `disallowTransferToParent: true` |

#### Code Pattern Translation

**Python (Current):**
```python
from google.adk.agents import Agent

agent = Agent(
    name="user_proxy_agent",
    model=get_model("user_proxy_agent"),
    instruction=get_dynamic_instruction,
    before_model_callback=[capture_user_query, inject_memories],
    after_model_callback=[save_memories_on_final_response],
    sub_agents=[prime_agent]
)
```

**TypeScript (Target):**
```typescript
import { LlmAgent, CallbackContext } from '@google/adk';

// Callback functions use the same pattern
function captureUserQuery({ context, request }: { context: CallbackContext; request: any }) {
  if (!context.session.state.originalUserQuery) {
    const userText = request.contents?.at(-1)?.parts?.[0]?.text ?? '';
    if (userText) {
      context.session.state.originalUserQuery = userText;
    }
  }
  return undefined; // Continue with request
}

function injectMemories({ context, request }: { context: CallbackContext; request: any }) {
  // Same logic as Python - search memories, inject into context
  const memories = await memoryService.search(context.session.state.originalUserQuery);
  // Modify request.config.systemInstruction to include memories
  return undefined;
}

// Agent definition - nearly identical to Python
const userProxyAgent = new LlmAgent({
  name: 'user_proxy_agent',
  model: 'gemini-2.5-flash', // or use Ollama via LiteLLM proxy
  instruction: getDynamicInstruction,
  beforeModelCallback: (args) => {
    captureUserQuery(args);
    return injectMemories(args);
  },
  afterModelCallback: saveMemoriesOnFinalResponse,
  subAgents: [primeAgent]
});
```

#### Performance Trade-offs

| Metric | Python (ADK) | TypeScript (ADK) |
|--------|--------------|------------------|
| Cold start | ~2-3s | ~200-500ms |
| Memory footprint | ~200MB | ~50-80MB |
| Streaming latency | ~50ms | ~20-30ms |
| Type safety | Runtime only | Compile + Runtime |
| API compatibility | N/A | **Near 1:1** |

**Risk:** LOW - Google ADK TypeScript is officially supported and API-compatible. Main considerations:
- Default model is Gemini; Ollama requires LiteLLM proxy or custom model adapter
- Some Python-specific features may have slightly different TypeScript APIs

---

### 3.2 Terminal UI (TUI)

**Current:** Textual (`textual` v6.5.0)
**Target:** Ink (`ink` v5.x) + ink-ui

#### Assumptions
- React paradigm (Ink) can replicate Textual's widget model
- Terminal capabilities (colors, styling, layout) are equivalent
- Streaming message updates work similarly

#### Architectural Changes

| Python (Textual) | TypeScript (Ink) |
|------------------|------------------|
| `App` class | `render(<App />)` |
| `compose()` method | JSX component tree |
| `@work(exclusive=True)` async workers | `useEffect` + async state |
| CSS-in-Python | Inline styles or chalk |
| `MessageList` widget | `<Box>` + map over messages |
| `Binding("ctrl+c", "quit")` | `useInput` hook |

#### Code Pattern Translation

**Python (Current):**
```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static

class AgentApp(App):
    BINDINGS = [Binding("ctrl+c", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield MessageList(id="feed")
        yield ChatInput(placeholder="Ask the agent...")
        yield Footer()

    @work(exclusive=True)
    async def _stream_agent_response(self, user_text: str):
        async for event in self._client.stream_run(user_text):
            if event.type == EventType.TEXT_MESSAGE_CONTENT:
                feed.append_to_message(event.message_id, event.delta)
```

**TypeScript (Target):**
```typescript
import React, { useState, useEffect } from 'react';
import { render, Box, Text, useInput, useApp } from 'ink';
import { TextInput } from '@inkjs/ui';

function AgentApp() {
  const { exit } = useApp();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);

  useInput((input, key) => {
    if (key.ctrl && input === 'c') exit();
  });

  async function handleSubmit(text: string) {
    setIsStreaming(true);
    setMessages(prev => [...prev, { role: 'user', content: text }]);

    const response = await fetch('/api/agent', {
      method: 'POST',
      body: JSON.stringify({ messages: [{ role: 'user', content: text }] })
    });

    // Handle SSE streaming
    const reader = response.body.getReader();
    // ... process events
    setIsStreaming(false);
  }

  return (
    <Box flexDirection="column" height="100%">
      <Box borderStyle="single" padding={1}>
        <Text bold>Solenoid</Text>
      </Box>
      <Box flexDirection="column" flexGrow={1}>
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
      </Box>
      <TextInput
        placeholder="Ask the agent..."
        value={input}
        onChange={setInput}
        onSubmit={handleSubmit}
      />
    </Box>
  );
}

render(<AgentApp />);
```

#### Performance Trade-offs

| Metric | Python (Textual) | TypeScript (Ink) |
|--------|------------------|------------------|
| Render speed | Good | Excellent (React reconciliation) |
| Memory usage | ~30MB | ~15-20MB |
| Color support | Full 24-bit | Full 24-bit (via chalk) |
| Layout system | CSS-like | Flexbox (Yoga) |
| Component reuse | Widget inheritance | React composition |

**Risk:** Textual has richer built-in widgets (LoadingIndicator, Modal screens). Ink requires more custom implementation or ink-ui package.

---

### 3.3 Web Server (Backend)

**Current:** FastAPI + Uvicorn
**Target:** Hono (recommended) or Fastify

#### Why Hono over Fastify?

| Feature | Hono | Fastify |
|---------|------|---------|
| Bundle size | ~14KB | ~2MB |
| SSE support | Built-in `streamSSE()` | Plugin required |
| TypeScript | First-class | Good |
| Runtime compatibility | Bun, Node, Deno, CF Workers | Node only |
| Performance | Excellent | Excellent |

#### Architectural Changes

| Python (FastAPI) | TypeScript (Hono) |
|------------------|-------------------|
| `@app.post("/api/agent")` | `app.post('/api/agent', handler)` |
| `StreamingResponse` | `streamSSE()` helper |
| `CORSMiddleware` | `cors()` middleware |
| Pydantic models | Zod schemas |
| `BackgroundTasks` | Native async |

#### Code Pattern Translation

**Python (Current):**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

@app.post("/api/agent")
async def run_agent(request: RunAgentInput):
    async def event_stream():
        async for event in agent_runner.run(request):
            yield f"data: {event.json()}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**TypeScript (Target):**
```typescript
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { streamSSE } from 'hono/streaming';
import { z } from 'zod';
import { zValidator } from '@hono/zod-validator';

const app = new Hono();
app.use('/*', cors());

const RunAgentInput = z.object({
  threadId: z.string(),
  messages: z.array(z.object({
    role: z.enum(['user', 'assistant']),
    content: z.string()
  }))
});

app.post('/api/agent', zValidator('json', RunAgentInput), async (c) => {
  const input = c.req.valid('json');

  return streamSSE(c, async (stream) => {
    await stream.writeSSE({ event: 'run-started', data: JSON.stringify({ runId: crypto.randomUUID() }) });

    for await (const event of agentRunner.run(input)) {
      await stream.writeSSE({
        event: event.type,
        data: JSON.stringify(event)
      });
    }

    await stream.writeSSE({ event: 'run-finished', data: '{}' });
  });
});

export default app;
```

#### Performance Trade-offs

| Metric | Python (FastAPI/Uvicorn) | TypeScript (Hono/Bun) |
|--------|--------------------------|----------------------|
| Requests/sec | ~15,000 | ~100,000+ |
| Latency (p99) | ~5ms | ~1ms |
| Memory per request | ~1MB | ~100KB |
| Cold start | ~500ms | ~50ms |
| SSE overhead | Low | Very low |

---

### 3.4 LLM Integration

**Current:** LiteLLM (`litellm` v1.79.3)
**Target:** Vercel AI SDK providers + Ollama JS SDK

#### Assumptions
- Primary backend remains Ollama for local inference
- OpenAI-compatible API support needed for flexibility
- Function calling (tool use) must be supported

#### Provider Mapping

| LiteLLM Provider | TypeScript Equivalent |
|------------------|----------------------|
| `ollama/model` | `@ai-sdk/ollama` or `ollama` package |
| `openai/model` | `@ai-sdk/openai` |
| `anthropic/model` | `@ai-sdk/anthropic` |
| Custom endpoints | `@ai-sdk/openai-compatible` |

#### Code Pattern Translation

**Python (Current):**
```python
from litellm import completion

response = completion(
    model="ollama/ministral-3:8b",
    messages=[{"role": "user", "content": "Hello"}],
    stream=True
)
for chunk in response:
    print(chunk.choices[0].delta.content)
```

**TypeScript (Target):**
```typescript
import { streamText } from 'ai';
import { ollama } from 'ollama-ai-provider';

const result = streamText({
  model: ollama('ministral-3:8b'),
  messages: [{ role: 'user', content: 'Hello' }]
});

for await (const chunk of result.textStream) {
  process.stdout.write(chunk);
}
```

#### Performance Trade-offs

| Metric | Python (LiteLLM) | TypeScript (AI SDK) |
|--------|------------------|---------------------|
| Provider switching | Excellent (100+ providers) | Good (20+ providers) |
| Streaming | Good | Excellent |
| Type safety | Runtime validation | Compile-time types |
| Bundle size | ~50MB | ~2MB |

**Risk:** LiteLLM has broader provider support. Some niche providers may need custom implementation.

---

### 3.5 Memory System (Vector Search)

**Current:** SQLite + sqlite-vec + FTS5 + BGE Reranker
**Target:** better-sqlite3 + sqlite-vec + FTS5 + Transformers.js

#### Assumptions
- SQLite remains the storage backend (no migration to external vector DB)
- sqlite-vec has Node.js bindings available
- BGE reranker can run via Transformers.js or Ollama

#### Architectural Changes

| Python Component | TypeScript Equivalent |
|------------------|----------------------|
| `sqlite3` + `sqlite-vec` | `better-sqlite3` + `sqlite-vec` |
| FTS5 (built-in) | FTS5 (built-in) |
| `OllamaEmbedder` | `ollama` package or Transformers.js |
| `FlagEmbedding` (BGE reranker) | Transformers.js `@huggingface/transformers` |
| Hybrid search (RRF) | Custom implementation (same algorithm) |

#### Code Pattern Translation

**Python (Current):**
```python
from flagembedding import FlagReranker

reranker = FlagReranker('BAAI/bge-reranker-v2-m3')
scores = reranker.compute_score([
    [query, doc1],
    [query, doc2]
])
```

**TypeScript (Target):**
```typescript
import { pipeline } from '@huggingface/transformers';

const reranker = await pipeline(
  'text-classification',
  'Xenova/bge-reranker-base'  // or hosted version
);

const scores = await Promise.all(
  documents.map(doc =>
    reranker(`${query} [SEP] ${doc}`).then(r => r[0].score)
  )
);
```

#### Embedding Generation

**Python (Current):**
```python
import ollama
embedding = ollama.embeddings(model='nomic-embed-text', prompt=text)
```

**TypeScript (Target - Option A: Ollama):**
```typescript
import { Ollama } from 'ollama';
const ollama = new Ollama();
const response = await ollama.embeddings({
  model: 'nomic-embed-text',
  prompt: text
});
const embedding = response.embedding;
```

**TypeScript (Target - Option B: Transformers.js):**
```typescript
import { pipeline } from '@huggingface/transformers';

const extractor = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2');
const output = await extractor(text, { pooling: 'mean', normalize: true });
const embedding = output.tolist()[0];
```

#### Performance Trade-offs

| Metric | Python (Current) | TypeScript (Ollama) | TypeScript (Transformers.js) |
|--------|------------------|---------------------|------------------------------|
| Embedding latency | ~50ms | ~50ms | ~100-200ms (first run), ~20ms (cached) |
| Reranking latency | ~100ms | N/A (use Ollama) | ~200-500ms |
| Memory (embedder) | ~500MB (model loaded) | ~0 (external) | ~200MB (WASM) |
| Offline capability | Yes (Ollama) | Yes (Ollama) | Yes (browser/Node) |

**Recommendation:** Use Ollama for embeddings (consistent with LLM), Transformers.js as fallback or for browser deployment.

---

### 3.6 Code Execution (WASM Sandbox)

**Current:** Wasmtime + Python 3.13 WASI
**Target:** Pyodide (recommended) or Wasmtime-JS

#### Why Pyodide over Wasmtime-JS?

| Feature | Pyodide | Wasmtime-JS |
|---------|---------|-------------|
| Python version | 3.11 | 3.13 (custom build) |
| Package ecosystem | micropip (PyPI subset) | Manual bundling |
| NumPy/Pandas | Yes (built-in) | Manual WASM builds |
| Pygal (charts) | Yes (via micropip) | Yes (bundled in python.wasm) |
| Setup complexity | Low | High |
| Security | Good (WASM sandbox) | Excellent (WASI fine-grained) |

#### Architectural Changes

| Python (Wasmtime) | TypeScript (Pyodide) |
|-------------------|----------------------|
| `WasmEngine` class | `loadPyodide()` + wrapper |
| `WasiConfig` for I/O | Pyodide's virtual filesystem |
| Fuel-based timeout | `pyodide.runPythonAsync` with AbortController |
| Context files via preopen | `pyodide.FS.writeFile()` |
| Output file capture | `pyodide.FS.readFile()` |

#### Code Pattern Translation

**Python (Current):**
```python
from wasmtime import Engine, Store, Module, Linker, WasiConfig

class WasmEngine:
    def run(self, code: str, context_files: dict = None) -> dict:
        wasi = WasiConfig()
        wasi.argv = ["python", "-c", code]
        wasi.preopen_dir(str(temp_dir), ".")
        wasi.stdout_file = str(stdout_path)

        instance = self.linker.instantiate(store, self.module)
        instance.exports(store)["_start"](store)

        return {"stdout": stdout_path.read_text(), "output_files": {...}}
```

**TypeScript (Target):**
```typescript
import { loadPyodide, PyodideInterface } from 'pyodide';

class PythonSandbox {
  private pyodide: PyodideInterface | null = null;

  async initialize() {
    this.pyodide = await loadPyodide({
      indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.0/full/'
    });
    // Install commonly used packages
    await this.pyodide.loadPackage(['micropip']);
    const micropip = this.pyodide.pyimport('micropip');
    await micropip.install('pygal');
  }

  async run(code: string, contextFiles?: Record<string, string>): Promise<ExecutionResult> {
    if (!this.pyodide) await this.initialize();

    // Write context files to virtual filesystem
    if (contextFiles) {
      for (const [name, content] of Object.entries(contextFiles)) {
        this.pyodide.FS.writeFile(name, content);
      }
    }

    // Capture stdout
    let stdout = '';
    this.pyodide.setStdout({ batched: (text) => { stdout += text; } });

    try {
      await this.pyodide.runPythonAsync(code);
      return { stdout, outcome: 'success', outputFiles: this.captureOutputFiles() };
    } catch (error) {
      return { stdout, stderr: String(error), outcome: 'error', outputFiles: {} };
    }
  }

  private captureOutputFiles(): Record<string, string> {
    // Read generated files from virtual filesystem
    const files: Record<string, string> = {};
    // ... enumerate FS and read non-input files
    return files;
  }
}
```

#### Performance Trade-offs

| Metric | Python (Wasmtime) | TypeScript (Pyodide) |
|--------|-------------------|----------------------|
| Cold start | ~500ms | ~2-3s (first load) |
| Execution speed | Near-native | ~3-5x slower than native |
| Memory | ~50MB | ~100-200MB |
| Package availability | Manual bundling | micropip (1000+ packages) |
| Isolation | WASI (excellent) | WASM (good) |
| Timeout support | Fuel-based (deterministic) | AbortController (wall-clock) |

**Risk:** Pyodide has larger memory footprint and slower cold start. Consider lazy loading or persistent worker.

---

### 3.7 MCP Integration

**Current:** Google ADK McpToolset
**Target:** `@modelcontextprotocol/sdk`

#### Assumptions
- Official MCP TypeScript SDK is feature-complete
- Both stdio and HTTP transports are supported
- Tool schemas are compatible with AI SDK

#### Architectural Changes

| Python (ADK MCP) | TypeScript (MCP SDK) |
|------------------|----------------------|
| `McpToolset(connection_params=...)` | `Client` + transport |
| `StdioConnectionParams` | `StdioClientTransport` |
| `StreamableHTTPConnectionParams` | `StreamableHTTPClientTransport` |
| Auto-discovery of tools | `client.listTools()` + manual registration |

#### Code Pattern Translation

**Python (Current):**
```python
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams

toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "@anthropic/mcp-filesystem"]
        )
    )
)

agent = Agent(name="mcp_agent", tools=[toolset])
```

**TypeScript (Target):**
```typescript
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { tool } from 'ai';
import { z } from 'zod';

class MCPToolManager {
  private clients: Map<string, Client> = new Map();

  async connectStdio(name: string, command: string, args: string[]) {
    const client = new Client({ name, version: '1.0.0' });
    const transport = new StdioClientTransport({ command, args });
    await client.connect(transport);
    this.clients.set(name, client);
  }

  async connectHTTP(name: string, url: string, headers?: Record<string, string>) {
    const client = new Client({ name, version: '1.0.0' });
    const transport = new StreamableHTTPClientTransport(new URL(url));
    await client.connect(transport);
    this.clients.set(name, client);
  }

  async getTools(): Promise<Record<string, ReturnType<typeof tool>>> {
    const tools: Record<string, ReturnType<typeof tool>> = {};

    for (const [serverName, client] of this.clients) {
      const { tools: mcpTools } = await client.listTools();

      for (const mcpTool of mcpTools) {
        tools[`${serverName}_${mcpTool.name}`] = tool({
          description: mcpTool.description || '',
          inputSchema: this.convertSchema(mcpTool.inputSchema),
          execute: async (args) => {
            const result = await client.callTool({ name: mcpTool.name, arguments: args });
            return result.content[0]?.text || JSON.stringify(result);
          }
        });
      }
    }

    return tools;
  }

  private convertSchema(jsonSchema: any): z.ZodType {
    // Convert JSON Schema to Zod schema
    // ... implementation
  }
}
```

#### Performance Trade-offs

| Metric | Python (ADK MCP) | TypeScript (MCP SDK) |
|--------|------------------|----------------------|
| Connection setup | ~100ms | ~50-100ms |
| Tool call latency | ~10ms overhead | ~5ms overhead |
| Memory per connection | ~20MB | ~10MB |
| Reconnection handling | Automatic | Manual implementation |

---

### 3.8 Configuration & Settings

**Current:** YAML + Pydantic validation
**Target:** YAML + Zod validation

#### Code Pattern Translation

**Python (Current):**
```python
import yaml
from pydantic import BaseModel, validator

class ModelConfig(BaseModel):
    provider: str
    model: str
    context_length: int = 128000

    @validator('provider')
    def valid_provider(cls, v):
        if v not in ['ollama', 'openai']:
            raise ValueError('Invalid provider')
        return v

with open('app_settings.yaml') as f:
    config = yaml.safe_load(f)
    validated = ModelConfig(**config['models']['default'])
```

**TypeScript (Target):**
```typescript
import { z } from 'zod';
import { parse } from 'yaml';
import { readFileSync } from 'fs';

const ModelConfig = z.object({
  provider: z.enum(['ollama', 'openai']),
  model: z.string(),
  context_length: z.number().default(128000)
});

const AppSettings = z.object({
  models: z.object({
    default: ModelConfig,
    agents: z.record(ModelConfig.optional())
  }),
  embeddings: z.object({
    provider: z.string(),
    model: z.string(),
    host: z.string().url()
  }),
  mcp_servers: z.record(z.union([
    z.object({ type: z.literal('stdio'), command: z.string(), args: z.array(z.string()) }),
    z.object({ type: z.literal('http'), url: z.string().url(), headers: z.record(z.string()).optional() })
  ]))
});

type Settings = z.infer<typeof AppSettings>;

function loadSettings(path: string): Settings {
  const content = readFileSync(path, 'utf-8');
  const raw = parse(content);
  return AppSettings.parse(raw);
}
```

---

## 4. Dependency Mapping

### Complete Dependency Translation Table

| Python Package | Version | TypeScript Equivalent | Version | Notes |
|----------------|---------|----------------------|---------|-------|
| `google-adk` | ^1.18.0 | `@google/adk` | ^0.2.0 | **API-compatible**, same patterns |
| `textual` | ^6.5.0 | `ink` + `@inkjs/ui` | ^5.0.0 | React paradigm vs class-based |
| `fastapi` | ^0.115.0 | `hono` | ^4.0.0 | Similar ergonomics |
| `uvicorn` | ^0.35.0 | (built into Hono/Bun) | - | Not needed separately |
| `litellm` | ^1.79.3 | `@ai-sdk/*` providers | various | Less provider coverage |
| `sqlite-vec` | ^0.1.6 | `sqlite-vec` (npm) | ^0.1.6 | Same package, JS bindings |
| `pydantic` | ^2.12.4 | `zod` | ^3.24.0 | Different API, similar concept |
| `numpy` | ^2.3.4 | (not needed) | - | Pyodide includes it |
| `wasmtime` | ^39.0.0 | `pyodide` | ^0.26.0 | Different approach |
| `ag-ui-adk` | ^0.3.6 | `@google/adk-devtools` | ^0.2.0 | Built-in web UI + CLI runner |
| `httpx` | ^0.27.0 | `fetch` (native) | - | Built into runtime |
| `flagembedding` | ^1.3.5 | `@huggingface/transformers` | ^3.0.0 | WASM-based, slower |
| `transformers` | ^4.45 | `@huggingface/transformers` | ^3.0.0 | Subset of models |
| `einops` | ^0.8.1 | (not needed) | - | Handled by Transformers.js |
| `pytest` | ^8.1.0 | `vitest` or `jest` | ^2.0.0 | Similar capabilities |
| `pyyaml` | (implicit) | `yaml` | ^2.4.0 | YAML parsing |

### New Dependencies (TypeScript-only)

| Package | Purpose |
|---------|---------|
| `@google/adk` | Agent Development Kit (core) |
| `@google/adk-devtools` | CLI runner + Web UI |
| `@google/genai` | Gemini/GenAI types |
| `better-sqlite3` | SQLite driver |
| `chalk` | Terminal colors |
| `commander` | CLI argument parsing |
| `tsx` | TypeScript execution |

**Note:** MCP is built into `@google/adk` via `McpToolset` - no separate `@modelcontextprotocol/sdk` needed.

---

## 5. Architectural Changes

### 5.1 Project Structure

**Current (Python):**
```
solenoid/
├── app/
│   ├── agent/
│   │   ├── prime_agent/
│   │   ├── planning_agent/
│   │   ├── code_executor_agent/
│   │   ├── memory/
│   │   └── local_execution/
│   ├── server/
│   ├── ui/
│   └── settings/
├── resources/
├── tests/
└── main_bundled.py
```

**Target (TypeScript):**
```
solenoid/
├── src/
│   ├── agents/
│   │   ├── user-proxy.ts
│   │   ├── prime.ts
│   │   ├── planning.ts
│   │   ├── code-executor.ts
│   │   ├── chart-generator.ts
│   │   ├── research.ts
│   │   ├── mcp.ts
│   │   └── generic.ts
│   ├── server/
│   │   ├── index.ts
│   │   └── agui-handler.ts
│   ├── ui/
│   │   ├── app.tsx
│   │   ├── components/
│   │   └── hooks/
│   ├── memory/
│   │   ├── service.ts
│   │   ├── embeddings.ts
│   │   ├── search.ts
│   │   └── rerank.ts
│   ├── sandbox/
│   │   └── pyodide-engine.ts
│   ├── mcp/
│   │   └── manager.ts
│   ├── config/
│   │   ├── settings.ts
│   │   └── schema.ts
│   └── index.ts
├── resources/
│   └── python-wasi/  (if keeping Wasmtime)
├── tests/
├── package.json
└── tsconfig.json
```

### 5.2 Concurrency Model Changes

**Python (asyncio):**
- Single-threaded event loop
- `async/await` for I/O
- `asyncio.gather()` for parallel tasks
- Background thread for TUI

**TypeScript (Node.js):**
- Single-threaded event loop (similar)
- `async/await` for I/O
- `Promise.all()` for parallel tasks
- Worker threads for CPU-intensive tasks (embeddings, reranking)

**Recommendation:** Use Worker threads for:
- Embedding generation (if using Transformers.js)
- Reranking operations
- Pyodide code execution (already isolated)

### 5.3 Error Handling Changes

**Python:**
```python
try:
    result = await agent.run(input)
except AgentError as e:
    logger.exception("Agent failed")
    raise HTTPException(status_code=500, detail=str(e))
```

**TypeScript:**
```typescript
import { HTTPException } from 'hono/http-exception';

try {
  const result = await agent.generate({ prompt: input });
} catch (error) {
  if (error instanceof AgentError) {
    throw new HTTPException(500, { message: error.message });
  }
  throw error;
}
```

### 5.4 Logging Changes

**Python (logging module):**
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Processing request")
```

**TypeScript (pino recommended):**
```typescript
import pino from 'pino';
const logger = pino({ name: 'solenoid' });
logger.info({ requestId }, 'Processing request');
```

---

## 6. Performance Trade-offs

### 6.1 Summary Comparison

| Metric | Python (Current) | TypeScript (Target) | Change |
|--------|------------------|---------------------|--------|
| **Startup Time** | 3-5s | <1s | -80% |
| **Memory Baseline** | ~200MB | ~80MB | -60% |
| **Memory Peak** | ~800MB | ~400MB | -50% |
| **HTTP Requests/sec** | ~15,000 | ~100,000 | +560% |
| **SSE Latency** | ~50ms | ~20ms | -60% |
| **Code Execution (cold)** | ~500ms | ~2-3s | +400% |
| **Code Execution (warm)** | ~100ms | ~100ms | 0% |
| **Embedding Generation** | ~50ms | ~50-200ms | 0-300% |
| **Reranking** | ~100ms | ~200-500ms | +100-400% |
| **Bundle Size** | ~500MB | ~100MB | -80% |

### 6.2 Trade-off Analysis

#### Wins
1. **Startup time**: Dramatically faster cold starts
2. **Memory**: Lower baseline and peak memory
3. **HTTP performance**: Much higher throughput
4. **Bundle size**: Easier distribution
5. **Type safety**: Compile-time error catching

#### Losses
1. **ML model inference**: Transformers.js is slower than native Python
2. **Code sandbox cold start**: Pyodide takes longer to initialize
3. **Reranking**: WASM-based BGE is slower than native
4. **Provider coverage**: LiteLLM has more LLM providers

#### Mitigations

| Loss | Mitigation Strategy |
|------|---------------------|
| Slow Transformers.js | Use Ollama for embeddings (consistent, fast) |
| Pyodide cold start | Pre-warm on server start, keep instance alive |
| Slow reranking | Use Ollama for reranking, or skip for small result sets |
| Provider coverage | Implement OpenAI-compatible fallback |

---

## 7. Risk Assessment

### 7.1 High-Risk Items

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Pyodide package compatibility | Some Python packages won't work | Medium | Test all required packages early |
| sqlite-vec Node bindings issues | Memory system breaks | Low | Have ChromaDB fallback ready |
| MCP SDK bugs/limitations | Tool integration fails | Low | Official SDK, can contribute fixes |

**Note:** With Google ADK TypeScript (`@google/adk`), the agent framework risk is now **LOW** instead of high. The API is compatible with the Python version.

### 7.2 Medium-Risk Items

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Ink complexity for rich TUI | Slower UI development | Medium | Use ink-ui components, accept simpler UI |
| BGE reranking performance | Search quality degrades | Medium | Fall back to no reranking, or use Ollama |
| AG-UI protocol changes | Breaking changes | Low | Pin protocol version, abstract implementation |

### 7.3 Low-Risk Items

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Hono SSE issues | Use Fastify instead | Very Low | Multiple alternatives available |
| Zod schema complexity | Minor refactoring | Low | Well-documented, large community |
| YAML parsing differences | Config bugs | Very Low | Use same yaml library behavior |

---

## 8. Migration Strategy

### 8.1 Phased Approach

**Phase 1: Foundation (2-3 weeks)**
- Set up TypeScript project structure
- Implement Zod config schemas
- Create Hono server with health endpoint
- Basic Ink TUI shell

**Phase 2: Core Agent (3-4 weeks)**
- Implement agent framework with AI SDK
- Port user_proxy → prime → planning hierarchy
- Implement memory injection/storage callbacks
- Basic streaming to TUI

**Phase 3: Memory System (2-3 weeks)**
- Port SQLite schema creation
- Implement hybrid search (sqlite-vec + FTS5)
- Ollama embeddings integration
- Optional: Transformers.js reranking

**Phase 4: Specialist Agents (3-4 weeks)**
- Code executor with Pyodide
- Chart generator (Pyodide + Pygal)
- Research agent (Brave Search)
- MCP agent (TypeScript SDK)
- Generic executor

**Phase 5: UI Polish (2-3 weeks)**
- Full message list with streaming
- Tool call visualization
- Settings screen
- Slash commands

**Phase 6: Testing & Optimization (2-3 weeks)**
- Port evaluation framework
- Performance optimization
- Bundle optimization
- Documentation

### 8.2 Parallel Development Approach

Run both Python and TypeScript versions simultaneously during development:

```
┌─────────────────────────────────────────────────┐
│                  Development                     │
├─────────────────────────────────────────────────┤
│  Python (Production)    │  TypeScript (Dev)     │
│  ─────────────────────  │  ─────────────────   │
│  Port 8000              │  Port 8001            │
│  Same Ollama backend    │  Same Ollama backend  │
│  Same SQLite DB         │  Shadow/Test DB       │
│  Same MCP servers       │  Same MCP servers     │
└─────────────────────────────────────────────────┘
```

### 8.3 Feature Parity Checklist

- [ ] User input → agent response flow
- [ ] Streaming text output
- [ ] Tool call visualization
- [ ] Memory injection (context recall)
- [ ] Memory storage (conversation persistence)
- [ ] Code execution (Python in WASM)
- [ ] Chart generation (SVG output)
- [ ] Web search (Brave API)
- [ ] MCP tool integration (stdio + HTTP)
- [ ] Settings management (YAML + validation)
- [ ] Slash commands (/settings, /help, /clear)
- [ ] Keyboard shortcuts (Ctrl+C, Ctrl+L)
- [ ] Error handling and recovery
- [ ] Logging and debugging

---

## 9. Testing Strategy

### 9.1 Unit Testing

**Framework:** Vitest (fast, TypeScript-native)

```typescript
// tests/memory/search.test.ts
import { describe, it, expect, beforeAll } from 'vitest';
import { MemoryService } from '../../src/memory/service';

describe('MemoryService', () => {
  let service: MemoryService;

  beforeAll(async () => {
    service = new MemoryService(':memory:');
    await service.initialize();
  });

  it('should store and retrieve memories', async () => {
    await service.addMemory({
      text: 'The user prefers dark mode',
      type: 'preference',
      userId: 'test-user'
    });

    const results = await service.search('dark mode', { userId: 'test-user' });
    expect(results).toHaveLength(1);
    expect(results[0].text).toContain('dark mode');
  });
});
```

### 9.2 Integration Testing

```typescript
// tests/integration/agent-flow.test.ts
import { describe, it, expect } from 'vitest';
import { createTestServer } from '../helpers/server';

describe('Agent Flow', () => {
  it('should complete a simple query', async () => {
    const server = await createTestServer();

    const response = await fetch(`${server.url}/api/agent`, {
      method: 'POST',
      body: JSON.stringify({
        threadId: 'test',
        messages: [{ role: 'user', content: 'What is 2+2?' }]
      })
    });

    const events = await collectSSEEvents(response);
    const textEvents = events.filter(e => e.type === 'TEXT_MESSAGE_CONTENT');
    const fullText = textEvents.map(e => e.delta).join('');

    expect(fullText).toContain('4');
  });
});
```

### 9.3 Evaluation Framework Port

Port the existing `tests/eval/run_eval.py` to TypeScript:

```typescript
// tests/eval/runner.ts
import { parse } from 'csv-parse/sync';
import { readFileSync, writeFileSync } from 'fs';

interface TestCase {
  id: string;
  category: string;
  input: string;
  expectedBehavior: string;
  gradingCriteria: string;
}

async function runEvaluation(cases: TestCase[], runs: number = 1) {
  const results: EvalResult[] = [];

  for (const testCase of cases) {
    for (let run = 0; run < runs; run++) {
      const response = await runAgent(testCase.input);
      const grade = await gradeResponse(response, testCase.gradingCriteria);
      results.push({ testCase, run, response, grade });
    }
  }

  return results;
}
```

---

## 10. Appendix: Library API Comparisons

### 10.1 Agent Definition

| Feature | Google ADK (Python) | Google ADK (TypeScript) |
|---------|---------------------|-------------------------|
| Basic agent | `Agent(name, model, instruction)` | `new LlmAgent({name, model, instruction})` |
| Tools | `tools=[tool1, tool2]` | `tools: [tool1, tool2]` |
| Sub-agents | `sub_agents=[agent1]` | `subAgents: [agent1]` |
| Callbacks | `before_model_callback`, `after_model_callback` | `beforeModelCallback`, `afterModelCallback` |
| Transfer control | `disallow_transfer_to_parent=True` | `disallowTransferToParent: true` |
| Streaming | Built-in via Runner | Built-in via `InMemoryRunner` |
| Session service | `runner.sessionService` | `runner.sessionService` |
| Tool definition | `FunctionTool` or `@tool` decorator | `FunctionTool` with Zod schema |

### 10.2 TUI Components

| Feature | Textual | Ink |
|---------|---------|-----|
| App container | `class MyApp(App)` | `function App() {}` |
| Layout | CSS-like | Flexbox |
| Text styling | `Text("hello", style="bold")` | `<Text bold>hello</Text>` |
| Input handling | `@on(Input.Submitted)` | `useInput((input, key) => {})` |
| Loading | `LoadingIndicator` | `<Spinner />` (ink-ui) |
| Modals | `push_screen(MyScreen())` | Custom with state |

### 10.3 HTTP Server

| Feature | FastAPI | Hono |
|---------|---------|------|
| Route definition | `@app.post("/path")` | `app.post('/path', handler)` |
| Request validation | Pydantic | Zod + `zValidator` |
| SSE streaming | `StreamingResponse` | `streamSSE()` |
| CORS | `CORSMiddleware` | `cors()` |
| Error handling | `HTTPException` | `HTTPException` |

### 10.4 Database Operations

| Feature | Python (sqlite3) | TypeScript (better-sqlite3) |
|---------|------------------|----------------------------|
| Connection | `sqlite3.connect(path)` | `new Database(path)` |
| Execute | `cursor.execute(sql, params)` | `db.prepare(sql).run(params)` |
| Query | `cursor.fetchall()` | `db.prepare(sql).all(params)` |
| Transaction | `with conn:` | `db.transaction(() => {})()` |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Jan 2026 | Claude | Initial comprehensive plan |
| 1.1 | Jan 2026 | Claude | **Major update**: Replaced Vercel AI SDK with Google ADK TypeScript (`@google/adk`). This provides API-compatible agent framework, dramatically reducing conversion complexity and risk. |

---

## Next Steps

1. **Review and approve** this conversion plan
2. **Prototype high-risk components** (AI SDK agents, Pyodide sandbox)
3. **Set up TypeScript project** with build tooling
4. **Begin Phase 1** implementation
5. **Establish CI/CD** for parallel testing

---

*This document should be treated as a living document and updated as the conversion progresses and new insights are gained.*
