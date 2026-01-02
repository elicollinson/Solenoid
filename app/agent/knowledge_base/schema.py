# app/agent/knowledge_base/schema.py
"""
Dynamic SQL schema generation for per-agent knowledge bases.

Each agent gets isolated tables with the naming convention:
- kb_{agent_name}_chunks: Main chunk storage
- kb_{agent_name}_fts: FTS5 full-text search
- kb_{agent_name}_vec: Vector embeddings for KNN

The schema mirrors the existing kb_chunks pattern but is isolated per agent.
"""

import re
import logging

LOGGER = logging.getLogger(__name__)

# Pattern for valid agent names (matches schema.py validation)
VALID_AGENT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_agent_name(agent_name: str) -> bool:
    """Validate that an agent name is safe for use in SQL identifiers."""
    return bool(VALID_AGENT_NAME.match(agent_name))


def get_table_names(agent_name: str) -> dict[str, str]:
    """
    Get the table names for an agent's knowledge base.

    Args:
        agent_name: The agent's name (must be validated)

    Returns:
        Dictionary with table name keys: chunks, fts, vec
    """
    if not validate_agent_name(agent_name):
        raise ValueError(f"Invalid agent name for KB tables: {agent_name}")

    return {
        "chunks": f"kb_{agent_name}_chunks",
        "fts": f"kb_{agent_name}_fts",
        "vec": f"kb_{agent_name}_vec",
    }


def generate_create_schema(agent_name: str) -> str:
    """
    Generate SQL to create all tables for an agent's knowledge base.

    Args:
        agent_name: The agent's name (must be validated)

    Returns:
        Complete SQL string to create the KB tables
    """
    tables = get_table_names(agent_name)

    # Using f-strings with validated names is safe here
    sql = f"""
-- Knowledge base tables for agent: {agent_name}
-- Created automatically when agent is loaded

-- Main chunk storage
CREATE TABLE IF NOT EXISTS {tables['chunks']} (
    id INTEGER PRIMARY KEY,
    doc_id TEXT NOT NULL,
    title TEXT,
    url TEXT,
    text TEXT NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    meta_json TEXT DEFAULT '{{}}',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_{agent_name}_kb_doc
ON {tables['chunks']}(doc_id);

-- FTS5 full-text search index
CREATE VIRTUAL TABLE IF NOT EXISTS {tables['fts']}
USING fts5(text, content={tables['chunks']}, content_rowid=id);

-- Triggers to sync FTS with chunks table
CREATE TRIGGER IF NOT EXISTS {agent_name}_kb_ai AFTER INSERT ON {tables['chunks']} BEGIN
    INSERT INTO {tables['fts']}(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS {agent_name}_kb_ad AFTER DELETE ON {tables['chunks']} BEGIN
    INSERT INTO {tables['fts']}({tables['fts']}, rowid, text)
    VALUES('delete', old.id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS {agent_name}_kb_au AFTER UPDATE ON {tables['chunks']} BEGIN
    INSERT INTO {tables['fts']}({tables['fts']}, rowid, text)
    VALUES('delete', old.id, old.text);
    INSERT INTO {tables['fts']}(rowid, text) VALUES (new.id, new.text);
END;

-- Vector embeddings for KNN search (256D like memory system)
CREATE VIRTUAL TABLE IF NOT EXISTS {tables['vec']}
USING vec0(embedding float[256], chunk_id int);
"""

    return sql


def generate_drop_schema(agent_name: str) -> str:
    """
    Generate SQL to drop all tables for an agent's knowledge base.

    Args:
        agent_name: The agent's name (must be validated)

    Returns:
        Complete SQL string to drop the KB tables
    """
    tables = get_table_names(agent_name)

    # Drop in reverse dependency order
    sql = f"""
-- Drop knowledge base tables for agent: {agent_name}

-- Drop triggers first
DROP TRIGGER IF EXISTS {agent_name}_kb_ai;
DROP TRIGGER IF EXISTS {agent_name}_kb_ad;
DROP TRIGGER IF EXISTS {agent_name}_kb_au;

-- Drop virtual tables
DROP TABLE IF EXISTS {tables['vec']};
DROP TABLE IF EXISTS {tables['fts']};

-- Drop index
DROP INDEX IF EXISTS idx_{agent_name}_kb_doc;

-- Drop main table
DROP TABLE IF EXISTS {tables['chunks']};
"""

    return sql


def generate_clear_data(agent_name: str) -> str:
    """
    Generate SQL to clear all data from an agent's KB (keep tables).

    Args:
        agent_name: The agent's name (must be validated)

    Returns:
        SQL string to delete all data
    """
    tables = get_table_names(agent_name)

    sql = f"""
-- Clear all data from KB for agent: {agent_name}
DELETE FROM {tables['vec']};
DELETE FROM {tables['chunks']};
"""

    return sql


def check_tables_exist_sql(agent_name: str) -> str:
    """
    Generate SQL to check if KB tables exist for an agent.

    Args:
        agent_name: The agent's name

    Returns:
        SQL that returns 1 if tables exist, 0 otherwise
    """
    tables = get_table_names(agent_name)

    return f"""
SELECT COUNT(*) FROM sqlite_master
WHERE type='table' AND name='{tables['chunks']}'
"""
