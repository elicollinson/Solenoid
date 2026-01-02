# Dynamic Agent Creation & Knowledge Base Implementation Plan

## Design Decisions (Finalized)

| Decision | Choice | Details |
|----------|--------|---------|
| **1. Agent Storage** | Separate Files (B) | `agents/` directory with individual YAML files per agent |
| **2. Creation Mechanism** | Wizard (Updated) | `/create-agent` command opens TUI wizard for guided creation |
| **3. KB Architecture** | Per-Agent Isolated (B) | Separate tables per agent for KNN/RAG retrieval |
| **4. Hot Reload** | Slash Command (C) | `/reload-agents` command triggers re-scan |
| **5. KB Population** | Hybrid (C) | Model uses tools to add content, user can also use API |
| **6. Agent Hierarchy** | Flat (A) | Dynamic agents added directly under `planning_agent` |
| **7. Tool Access** | Explicit Selection (B) | Agent YAML specifies tools + MCP servers allowed |

---

## Architecture Overview

```
agents/                          # New directory for custom agent definitions
├── legal_research_agent.yaml
├── code_review_agent.yaml
└── ...

app/agent/
├── custom_agents/               # New module for dynamic agent system
│   ├── __init__.py
│   ├── schema.py               # Pydantic models for agent YAML
│   ├── loader.py               # Agent discovery and loading
│   ├── registry.py             # Runtime agent registry with reload
│   ├── factory.py              # Creates ADK Agent from schema
│   └── tools/                  # Agent creation/management tools
│       ├── __init__.py
│       ├── propose_agent.py    # Tool for model to propose agents
│       └── research_kb.py      # Tool for KB population
│
├── knowledge_base/              # New module for per-agent KB
│   ├── __init__.py
│   ├── schema.py               # Dynamic table schema generation
│   ├── manager.py              # KB lifecycle management
│   ├── ingestion.py            # Content fetching, chunking, embedding
│   └── search.py               # Scoped search for agent KBs
```

---

## Agent YAML Schema

```yaml
# agents/example_agent.yaml
name: legal_research_agent
description: "Specializes in legal document analysis and research"
instruction: |
  You are an expert legal researcher with deep knowledge of contract law,
  regulatory compliance, and case law analysis.

  When analyzing documents:
  1. Identify key legal terms and obligations
  2. Flag potential compliance issues
  3. Provide relevant precedents when available

# Optional: Override default model
model:
  name: gpt-oss:20b
  provider: ollama_chat

# Explicit tool access (available tools listed in registry)
tools:
  - universal_search
  - read_webpage
  # Note: code execution NOT included - principle of least privilege

# MCP server access (must be configured in app_settings.yaml)
mcp_servers:
  - filesystem
  # - context7  # Commented = not available to this agent

# Knowledge base configuration
knowledge_base:
  enabled: true
  # Search parameters for this agent's KB
  search_top_k: 10
  search_threshold: 0.7

# Optional metadata
metadata:
  author: user
  created_at: 2025-01-02
  version: 1
  tags: [legal, research, contracts]

# Agent state (managed by system)
enabled: true
```

---

## Pydantic Schema Definition

```python
# app/agent/custom_agents/schema.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class AgentModelConfig(BaseModel):
    name: str
    provider: str = "ollama_chat"

class AgentKBConfig(BaseModel):
    enabled: bool = True
    search_top_k: int = 10
    search_threshold: float = 0.7

class AgentMetadata(BaseModel):
    author: str = "user"
    created_at: datetime = Field(default_factory=datetime.now)
    version: int = 1
    tags: list[str] = []

class CustomAgentSchema(BaseModel):
    name: str = Field(..., pattern=r'^[a-z][a-z0-9_]*$')  # Valid identifier
    description: str
    instruction: str
    model: Optional[AgentModelConfig] = None
    tools: list[str] = []
    mcp_servers: list[str] = []
    knowledge_base: AgentKBConfig = AgentKBConfig()
    metadata: AgentMetadata = AgentMetadata()
    enabled: bool = True

    class Config:
        extra = "forbid"  # Catch typos in YAML
```

---

## Per-Agent Knowledge Base Schema

Each agent gets isolated tables with naming convention `kb_{agent_name}_*`:

```sql
-- Generated dynamically for each agent
-- Example for agent "legal_research_agent"

CREATE TABLE IF NOT EXISTS kb_legal_research_agent_chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,           -- Groups chunks from same document
    title TEXT,                      -- Document/source title
    url TEXT,                        -- Source URL if applicable
    text TEXT NOT NULL,              -- Chunk content
    chunk_index INTEGER DEFAULT 0,   -- Order within document
    meta_json TEXT,                  -- Additional metadata (JSON)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kb_legal_research_agent_doc
ON kb_legal_research_agent_chunks(doc_id);

-- FTS5 for keyword search
CREATE VIRTUAL TABLE IF NOT EXISTS kb_legal_research_agent_fts
USING fts5(text, content=kb_legal_research_agent_chunks, content_rowid=rowid);

-- Triggers to sync FTS
CREATE TRIGGER IF NOT EXISTS kb_legal_research_agent_ai AFTER INSERT ON kb_legal_research_agent_chunks BEGIN
    INSERT INTO kb_legal_research_agent_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS kb_legal_research_agent_ad AFTER DELETE ON kb_legal_research_agent_chunks BEGIN
    INSERT INTO kb_legal_research_agent_fts(kb_legal_research_agent_fts, rowid, text)
    VALUES('delete', old.rowid, old.text);
END;

CREATE TRIGGER IF NOT EXISTS kb_legal_research_agent_au AFTER UPDATE ON kb_legal_research_agent_chunks BEGIN
    INSERT INTO kb_legal_research_agent_fts(kb_legal_research_agent_fts, rowid, text)
    VALUES('delete', old.rowid, old.text);
    INSERT INTO kb_legal_research_agent_fts(rowid, text) VALUES (new.rowid, new.text);
END;

-- Vector table for embeddings (256D like existing memory system)
CREATE VIRTUAL TABLE IF NOT EXISTS kb_legal_research_agent_vec
USING vec0(embedding float[256]);
```

---

## Potential Issues & Mitigations

### 1. Agent Name Validation
**Issue**: Agent names with special characters break SQL table names.
**Mitigation**: Strict regex validation `^[a-z][a-z0-9_]*$` in schema.

### 2. Race Conditions on Reload
**Issue**: Reload during active request could cause inconsistent state.
**Mitigation**:
- Reload creates new agent instances, doesn't mutate existing
- Active requests continue with old agents
- New requests get new agents
- Use copy-on-write pattern for registry

### 3. Embedding Model Consistency
**Issue**: If embedding config changes, old vectors become incompatible.
**Mitigation**:
- Store embedding model info in KB metadata
- Warn/block if model mismatch detected
- Provide re-embed command for migration

### 4. MCP Server Availability
**Issue**: Agent requests MCP server that's not configured/running.
**Mitigation**:
- Validate MCP servers against `app_settings.yaml` at load time
- Log warning for unavailable servers
- Agent still loads but without those tools

### 5. Circular Dependencies
**Issue**: Agent loading needs settings, tools need agents.
**Mitigation**:
- Clear initialization order: settings → tools → agents
- Lazy loading for optional dependencies
- Dependency injection pattern

### 6. Planning Agent Context Length
**Issue**: Many agents = long instruction = context overflow.
**Mitigation**:
- Compact agent descriptions in instruction
- Consider two-stage routing (category → specific agent)
- Monitor and warn if instruction exceeds threshold

### 7. KB Table Cleanup
**Issue**: Deleting agent leaves orphan tables.
**Mitigation**:
- Agent deletion explicitly drops KB tables
- Startup scan for orphan tables (tables without agent file)
- `/kb-cleanup` command for manual cleanup

### 8. Tool Validation
**Issue**: Agent requests tool that doesn't exist.
**Mitigation**:
- Validate tools against registry at load time
- Clear error message with available tools list
- Agent loads with available tools only (warn about missing)

### 9. Concurrent KB Writes
**Issue**: Multiple requests writing to same agent's KB.
**Mitigation**:
- SQLite handles concurrent writes with WAL mode
- Use transactions for multi-chunk ingestion
- Consider write queue for heavy ingestion

### 10. Session State for Proposals
**Issue**: Agent proposal spans multiple turns, needs state.
**Mitigation**:
- Store pending proposals in session state
- Clear proposals on timeout or explicit cancel
- Use unique proposal IDs for tracking

---

## Implementation Phases

### Phase 1: Agent Schema & Loader Foundation
**Files to create/modify:**
- `app/agent/custom_agents/__init__.py`
- `app/agent/custom_agents/schema.py`
- `app/agent/custom_agents/loader.py`
- `agents/.gitkeep`
- `agents/_example.yaml` (template, disabled by default)

**Tasks:**
1. Create Pydantic schema for agent YAML
2. Implement agent file discovery (glob `agents/*.yaml`)
3. Implement YAML parsing with validation
4. Create sample/template agent file
5. Add unit tests for schema validation

**Exit criteria:** Can load and validate agent YAML files

---

### Phase 2: Agent Integration with Planning Agent
**Files to create/modify:**
- `app/agent/custom_agents/registry.py`
- `app/agent/custom_agents/factory.py`
- `app/agent/planning_agent/agent.py` (modify)
- `app/agent/planning_agent/dynamic_instruction.py` (new)

**Tasks:**
1. Create tool registry mapping names → FunctionTool instances
2. Implement MCP tool filtering per agent
3. Create ADK Agent factory from schema
4. Modify planning_agent to include dynamic sub_agents
5. Implement dynamic instruction generation
6. Wire up at server startup

**Exit criteria:** Dynamic agents appear in planning_agent and can be delegated to

---

### Phase 3: Reload Command Implementation
**Files to create/modify:**
- `app/agent/custom_agents/registry.py` (add reload)
- `app/ui/chat_input/__init__.py` (add command)
- `app/server/main.py` (add reload mechanism)

**Tasks:**
1. Add `/reload-agents` to chat input command handler
2. Implement registry reload (re-scan, re-parse, re-create)
3. Backend mechanism to trigger reload (could be in-memory signal)
4. TUI feedback on reload success/failure with agent count
5. Handle reload errors gracefully

**Exit criteria:** `/reload-agents` command works and updates available agents

---

### Phase 4: Per-Agent Knowledge Base System
**Files to create/modify:**
- `app/agent/knowledge_base/__init__.py`
- `app/agent/knowledge_base/schema.py`
- `app/agent/knowledge_base/manager.py`
- `app/agent/knowledge_base/search.py`
- `app/agent/memory/adk_sqlite_memory.py` (modify for KB support)

**Tasks:**
1. Dynamic table schema generator
2. KB lifecycle manager (create tables on agent create)
3. KB CRUD operations (add_chunks, search, delete_doc, clear)
4. Scoped hybrid search (dense + sparse + rerank)
5. Integration with agent's before_model_callback for RAG injection
6. KB deletion on agent removal

**Exit criteria:** Agents can search their isolated knowledge bases

---

### Phase 5: Agent Creation Tool (propose_agent)
**Files to create/modify:**
- `app/agent/custom_agents/tools/__init__.py`
- `app/agent/custom_agents/tools/propose_agent.py`
- `app/ui/agent_proposal/` (new TUI component)
- `app/agent/planning_agent/agent.py` (add tool)

**Tasks:**
1. `propose_agent` FunctionTool implementation
2. Proposal state management (session state)
3. TUI modal for proposal review
4. Edit capability before confirmation
5. File creation on approval
6. Automatic reload after creation
7. Validation and error feedback

**Exit criteria:** Model can propose agents, user can review/edit/approve

---

### Phase 6: KB Population Tool (research_for_kb)
**Files to create/modify:**
- `app/agent/custom_agents/tools/research_kb.py`
- `app/agent/knowledge_base/ingestion.py`
- `app/ui/kb_ingestion/` (new TUI component)

**Tasks:**
1. `research_for_kb` tool (search, find sources, propose)
2. `add_to_kb` tool (direct URL/content addition)
3. Source proposal state management
4. TUI modal for source review
5. Ingestion pipeline (fetch → chunk → embed → store)
6. Progress tracking and feedback
7. Chunking strategy (size, overlap)

**Exit criteria:** Model can propose sources, user approves, content ingested

---

### Phase 7: Agent Management Commands
**Files to create/modify:**
- `app/ui/chat_input/__init__.py` (add commands)
- `app/agent/custom_agents/registry.py` (add management)
- `app/agent/knowledge_base/manager.py` (add stats)

**Tasks:**
1. `/agents` - List all agents with status
2. `/agent-info <name>` - Show agent details
3. `/agent-disable <name>` - Disable without deleting
4. `/agent-enable <name>` - Re-enable
5. `/agent-delete <name>` - Delete with KB cleanup confirmation
6. `/kb-stats <agent>` - Show KB statistics
7. `/kb-clear <agent>` - Clear KB with confirmation

**Exit criteria:** Full agent lifecycle management via commands

---

## File Structure Summary

```
Solenoid/
├── agents/                           # NEW: Custom agent definitions
│   ├── .gitkeep
│   └── _example.yaml                 # Template (disabled)
│
├── app/
│   ├── agent/
│   │   ├── custom_agents/            # NEW: Dynamic agent system
│   │   │   ├── __init__.py
│   │   │   ├── schema.py             # Pydantic models
│   │   │   ├── loader.py             # File discovery & parsing
│   │   │   ├── registry.py           # Runtime registry
│   │   │   ├── factory.py            # Agent instantiation
│   │   │   └── tools/
│   │   │       ├── __init__.py
│   │   │       ├── propose_agent.py
│   │   │       └── research_kb.py
│   │   │
│   │   ├── knowledge_base/           # NEW: Per-agent KB system
│   │   │   ├── __init__.py
│   │   │   ├── schema.py             # Dynamic SQL generation
│   │   │   ├── manager.py            # Lifecycle management
│   │   │   ├── ingestion.py          # Content processing
│   │   │   └── search.py             # Scoped search
│   │   │
│   │   └── planning_agent/
│   │       ├── agent.py              # MODIFY: Dynamic sub_agents
│   │       └── dynamic_instruction.py # NEW: Instruction generator
│   │
│   └── ui/
│       ├── chat_input/
│       │   └── __init__.py           # MODIFY: Add commands
│       ├── agent_proposal/           # NEW: Proposal review UI
│       │   └── ...
│       └── kb_ingestion/             # NEW: Source review UI
│           └── ...
│
└── docs/
    └── DYNAMIC_AGENTS_IMPLEMENTATION_PLAN.md  # This file
```

---

## Testing Strategy

### Unit Tests
- Schema validation (valid/invalid YAML)
- Agent name sanitization
- Tool registry lookups
- KB table name generation
- Chunk splitting logic

### Integration Tests
- Agent loading and registration
- Dynamic agent delegation
- KB CRUD operations
- Hybrid search accuracy
- Reload without breaking active sessions

### End-to-End Tests
- Create agent via tool → approve → use
- Populate KB → search → get relevant results
- Full lifecycle: create → use → delete

---

## Rollout Plan

1. **Phase 1-2**: Core functionality, manual YAML editing only
2. **Phase 3**: Reload command for iteration
3. **Phase 4**: KB system, agents become useful
4. **Phase 5**: Model-assisted creation
5. **Phase 6**: Model-assisted KB population
6. **Phase 7**: Full management suite

Each phase is independently useful - can ship incrementally.
