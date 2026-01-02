# app/agent/knowledge_base/manager.py
"""
Knowledge base lifecycle manager.

Handles:
- Creating KB tables when agents are loaded
- Dropping KB tables when agents are deleted
- CRUD operations for KB chunks
- Statistics and monitoring
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.agent.knowledge_base.schema import (
    generate_create_schema,
    generate_drop_schema,
    generate_clear_data,
    check_tables_exist_sql,
    get_table_names,
    validate_agent_name,
)
from app.agent.memory.ollama_embeddings import OllamaEmbedder, CROP_DIM
from app.agent.config import get_embedding_config

LOGGER = logging.getLogger(__name__)

# Default database path (same as memory service)
DEFAULT_DB_PATH = "memories.db"


@dataclass
class KBStats:
    """Statistics for an agent's knowledge base."""

    agent_name: str
    chunk_count: int
    doc_count: int
    total_text_length: int
    has_embeddings: bool
    embedding_count: int


@dataclass
class ChunkData:
    """Data for a KB chunk."""

    doc_id: str
    title: Optional[str]
    url: Optional[str]
    text: str
    chunk_index: int = 0
    meta: Optional[dict] = None


class KnowledgeBaseManager:
    """
    Manages knowledge bases for custom agents.

    Provides lifecycle management (create/delete) and CRUD operations
    for agent-specific knowledge bases.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._embedder: Optional[OllamaEmbedder] = None
        self._initialized_agents: set[str] = set()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with sqlite-vec loaded."""
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        import sqlite_vec

        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    def _get_embedder(self) -> OllamaEmbedder:
        """Get or create the embedder instance using Ollama config."""
        if self._embedder is None:
            embed_config = get_embedding_config()
            self._embedder = OllamaEmbedder(
                host=embed_config["host"],
                model=embed_config["model"],
            )
        return self._embedder

    def create_kb_for_agent(self, agent_name: str) -> bool:
        """
        Create knowledge base tables for an agent.

        Args:
            agent_name: The agent's name (must be valid identifier)

        Returns:
            True if created successfully, False if already exists
        """
        if not validate_agent_name(agent_name):
            raise ValueError(f"Invalid agent name: {agent_name}")

        conn = self._get_connection()
        try:
            # Check if tables already exist
            check_sql = check_tables_exist_sql(agent_name)
            result = conn.execute(check_sql).fetchone()

            if result and result[0] > 0:
                LOGGER.debug(f"KB tables already exist for agent: {agent_name}")
                self._initialized_agents.add(agent_name)
                return False

            # Create tables
            create_sql = generate_create_schema(agent_name)
            conn.executescript(create_sql)
            conn.commit()

            self._initialized_agents.add(agent_name)
            LOGGER.info(f"Created KB tables for agent: {agent_name}")
            return True

        except Exception as e:
            LOGGER.error(f"Failed to create KB for agent {agent_name}: {e}")
            raise
        finally:
            conn.close()

    def delete_kb_for_agent(self, agent_name: str) -> bool:
        """
        Delete knowledge base tables for an agent.

        Args:
            agent_name: The agent's name

        Returns:
            True if deleted, False if didn't exist
        """
        if not validate_agent_name(agent_name):
            raise ValueError(f"Invalid agent name: {agent_name}")

        conn = self._get_connection()
        try:
            # Check if tables exist
            check_sql = check_tables_exist_sql(agent_name)
            result = conn.execute(check_sql).fetchone()

            if not result or result[0] == 0:
                LOGGER.debug(f"KB tables don't exist for agent: {agent_name}")
                return False

            # Drop tables
            drop_sql = generate_drop_schema(agent_name)
            conn.executescript(drop_sql)
            conn.commit()

            self._initialized_agents.discard(agent_name)
            LOGGER.info(f"Deleted KB tables for agent: {agent_name}")
            return True

        except Exception as e:
            LOGGER.error(f"Failed to delete KB for agent {agent_name}: {e}")
            raise
        finally:
            conn.close()

    def clear_kb_for_agent(self, agent_name: str) -> int:
        """
        Clear all data from an agent's KB (keep tables).

        Args:
            agent_name: The agent's name

        Returns:
            Number of chunks deleted
        """
        if not validate_agent_name(agent_name):
            raise ValueError(f"Invalid agent name: {agent_name}")

        conn = self._get_connection()
        try:
            tables = get_table_names(agent_name)

            # Get count before delete
            count = conn.execute(
                f"SELECT COUNT(*) FROM {tables['chunks']}"
            ).fetchone()[0]

            # Clear data
            clear_sql = generate_clear_data(agent_name)
            conn.executescript(clear_sql)
            conn.commit()

            LOGGER.info(f"Cleared {count} chunks from KB for agent: {agent_name}")
            return count

        except Exception as e:
            LOGGER.error(f"Failed to clear KB for agent {agent_name}: {e}")
            raise
        finally:
            conn.close()

    def add_chunk(
        self,
        agent_name: str,
        chunk: ChunkData,
        embed: bool = True,
    ) -> int:
        """
        Add a single chunk to an agent's KB.

        Args:
            agent_name: The agent's name
            chunk: The chunk data to add
            embed: Whether to compute and store embedding

        Returns:
            The chunk ID
        """
        if not validate_agent_name(agent_name):
            raise ValueError(f"Invalid agent name: {agent_name}")

        conn = self._get_connection()
        try:
            tables = get_table_names(agent_name)

            # Insert chunk
            meta_json = json.dumps(chunk.meta or {})
            cursor = conn.execute(
                f"""
                INSERT INTO {tables['chunks']}
                (doc_id, title, url, text, chunk_index, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.doc_id,
                    chunk.title,
                    chunk.url,
                    chunk.text,
                    chunk.chunk_index,
                    meta_json,
                ),
            )
            chunk_id = cursor.lastrowid

            # Compute and store embedding
            if embed:
                embedder = self._get_embedder()
                vec = embedder.embed_doc(chunk.text)
                blob = embedder.to_blob(vec)

                conn.execute(
                    f"""
                    INSERT INTO {tables['vec']} (rowid, embedding, chunk_id)
                    VALUES (?, ?, ?)
                    """,
                    (chunk_id, blob, chunk_id),
                )

            conn.commit()
            return chunk_id

        except Exception as e:
            LOGGER.error(f"Failed to add chunk to KB for agent {agent_name}: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def add_chunks(
        self,
        agent_name: str,
        chunks: list[ChunkData],
        embed: bool = True,
    ) -> list[int]:
        """
        Add multiple chunks to an agent's KB in a single transaction.

        Args:
            agent_name: The agent's name
            chunks: List of chunk data to add
            embed: Whether to compute and store embeddings

        Returns:
            List of chunk IDs
        """
        if not validate_agent_name(agent_name):
            raise ValueError(f"Invalid agent name: {agent_name}")

        if not chunks:
            return []

        conn = self._get_connection()
        embedder = self._get_embedder() if embed else None

        try:
            tables = get_table_names(agent_name)
            chunk_ids = []

            for chunk in chunks:
                meta_json = json.dumps(chunk.meta or {})
                cursor = conn.execute(
                    f"""
                    INSERT INTO {tables['chunks']}
                    (doc_id, title, url, text, chunk_index, meta_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.doc_id,
                        chunk.title,
                        chunk.url,
                        chunk.text,
                        chunk.chunk_index,
                        meta_json,
                    ),
                )
                chunk_id = cursor.lastrowid
                chunk_ids.append(chunk_id)

                if embedder:
                    vec = embedder.embed_doc(chunk.text)
                    blob = embedder.to_blob(vec)
                    conn.execute(
                        f"""
                        INSERT INTO {tables['vec']} (rowid, embedding, chunk_id)
                        VALUES (?, ?, ?)
                        """,
                        (chunk_id, blob, chunk_id),
                    )

            conn.commit()
            LOGGER.info(
                f"Added {len(chunks)} chunks to KB for agent: {agent_name}"
            )
            return chunk_ids

        except Exception as e:
            LOGGER.error(f"Failed to add chunks to KB for agent {agent_name}: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_document(self, agent_name: str, doc_id: str) -> int:
        """
        Delete all chunks for a document.

        Args:
            agent_name: The agent's name
            doc_id: The document ID to delete

        Returns:
            Number of chunks deleted
        """
        if not validate_agent_name(agent_name):
            raise ValueError(f"Invalid agent name: {agent_name}")

        conn = self._get_connection()
        try:
            tables = get_table_names(agent_name)

            # Get chunk IDs to delete from vec table
            chunk_ids = conn.execute(
                f"SELECT id FROM {tables['chunks']} WHERE doc_id = ?",
                (doc_id,),
            ).fetchall()

            if not chunk_ids:
                return 0

            # Delete from vec table
            ids_tuple = tuple(row[0] for row in chunk_ids)
            placeholders = ",".join("?" * len(ids_tuple))
            conn.execute(
                f"DELETE FROM {tables['vec']} WHERE chunk_id IN ({placeholders})",
                ids_tuple,
            )

            # Delete from chunks (triggers handle FTS)
            cursor = conn.execute(
                f"DELETE FROM {tables['chunks']} WHERE doc_id = ?",
                (doc_id,),
            )
            count = cursor.rowcount

            conn.commit()
            LOGGER.info(f"Deleted {count} chunks for doc {doc_id} from agent {agent_name}")
            return count

        except Exception as e:
            LOGGER.error(f"Failed to delete document from KB: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_stats(self, agent_name: str) -> KBStats:
        """
        Get statistics for an agent's KB.

        Args:
            agent_name: The agent's name

        Returns:
            KBStats object with counts and info
        """
        if not validate_agent_name(agent_name):
            raise ValueError(f"Invalid agent name: {agent_name}")

        conn = self._get_connection()
        try:
            tables = get_table_names(agent_name)

            # Check if tables exist
            check_sql = check_tables_exist_sql(agent_name)
            result = conn.execute(check_sql).fetchone()

            if not result or result[0] == 0:
                return KBStats(
                    agent_name=agent_name,
                    chunk_count=0,
                    doc_count=0,
                    total_text_length=0,
                    has_embeddings=False,
                    embedding_count=0,
                )

            # Get counts
            chunk_count = conn.execute(
                f"SELECT COUNT(*) FROM {tables['chunks']}"
            ).fetchone()[0]

            doc_count = conn.execute(
                f"SELECT COUNT(DISTINCT doc_id) FROM {tables['chunks']}"
            ).fetchone()[0]

            text_length = conn.execute(
                f"SELECT COALESCE(SUM(LENGTH(text)), 0) FROM {tables['chunks']}"
            ).fetchone()[0]

            embedding_count = conn.execute(
                f"SELECT COUNT(*) FROM {tables['vec']}"
            ).fetchone()[0]

            return KBStats(
                agent_name=agent_name,
                chunk_count=chunk_count,
                doc_count=doc_count,
                total_text_length=text_length,
                has_embeddings=embedding_count > 0,
                embedding_count=embedding_count,
            )

        except Exception as e:
            LOGGER.error(f"Failed to get KB stats for agent {agent_name}: {e}")
            raise
        finally:
            conn.close()

    def ensure_kb_exists(self, agent_name: str) -> None:
        """
        Ensure KB tables exist for an agent (create if needed).

        Args:
            agent_name: The agent's name
        """
        if agent_name in self._initialized_agents:
            return
        self.create_kb_for_agent(agent_name)


# Global manager instance
_manager: Optional[KnowledgeBaseManager] = None


def get_kb_manager(db_path: str = DEFAULT_DB_PATH) -> KnowledgeBaseManager:
    """Get the global KB manager instance."""
    global _manager
    if _manager is None:
        _manager = KnowledgeBaseManager(db_path=db_path)
    return _manager


def reset_kb_manager() -> None:
    """Reset the global manager (for testing)."""
    global _manager
    _manager = None
