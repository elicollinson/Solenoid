"""SQLite-backed conversation store and context window manager."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Sequence


CREATE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        created_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS responses (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        parent_response_id TEXT,
        created_at INTEGER NOT NULL,
        model TEXT NOT NULL,
        instructions TEXT,
        input_json TEXT NOT NULL,
        output_json TEXT,
        last_message_turn INTEGER,
        FOREIGN KEY (conversation_id) REFERENCES conversations (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        turn_index INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES conversations (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS compaction_state (
        conversation_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        updated_at INTEGER NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES conversations (id)
    )
    """,
]


class ConversationStore:
    """Persistence layer handling conversations, messages, and responses."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._configure_connection()
        self._init_schema()

    def _configure_connection(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")

    def _init_schema(self) -> None:
        with self._conn:
            for statement in CREATE_TABLES_SQL:
                self._conn.execute(statement)

    def close(self) -> None:
        self._conn.close()

    def ensure_conversation(self, conversation_id: str | None = None) -> str:
        conversation_id = conversation_id or f"conv_{uuid.uuid4().hex}"
        created_at = int(time.time())
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO conversations (id, created_at) VALUES (?, ?)",
                (conversation_id, created_at),
            )
        return conversation_id

    def get_conversation_id_for_response(self, response_id: str) -> str | None:
        cur = self._conn.execute(
            "SELECT conversation_id FROM responses WHERE id=?",
            (response_id,),
        )
        row = cur.fetchone()
        return row["conversation_id"] if row else None

    def append_messages(self, conversation_id: str, messages: Sequence[dict[str, Any]]) -> int:
        created_at = int(time.time())
        with self._lock, self._conn:
            cur = self._conn.execute(
                "SELECT COALESCE(MAX(turn_index), -1) AS max_turn FROM messages WHERE conversation_id=?",
                (conversation_id,),
            )
            row = cur.fetchone()
            next_turn = (row["max_turn"] if row else -1) + 1

            last_turn = next_turn - 1
            for message in messages:
                content_json = json.dumps(message.get("content"))
                self._conn.execute(
                    """
                    INSERT INTO messages (conversation_id, role, content, turn_index, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        message.get("role"),
                        content_json,
                        next_turn,
                        created_at,
                    ),
                )
                last_turn = next_turn
                next_turn += 1

        return last_turn

    def record_response(
        self,
        response_id: str,
        conversation_id: str,
        parent_response_id: str | None,
        model: str,
        instructions: str | None,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any] | None,
        last_message_turn: int | None,
    ) -> None:
        created_at = int(time.time())
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO responses (
                    id, conversation_id, parent_response_id, created_at,
                    model, instructions, input_json, output_json, last_message_turn
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response_id,
                    conversation_id,
                    parent_response_id,
                    created_at,
                    model,
                    instructions,
                    json.dumps(input_payload),
                    json.dumps(output_payload) if output_payload is not None else None,
                    last_message_turn,
                ),
            )

    def get_messages(
        self,
        conversation_id: str,
        up_to_turn: int | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT id, role, content, turn_index, created_at FROM messages WHERE conversation_id=?"
        params: list[Any] = [conversation_id]
        if up_to_turn is not None:
            query += " AND turn_index <= ?"
            params.append(up_to_turn)
        query += " ORDER BY turn_index ASC"

        cur = self._conn.execute(query, params)
        messages = []
        for row in cur.fetchall():
            try:
                content = json.loads(row["content"])
            except json.JSONDecodeError:
                content = row["content"]
            messages.append(
                {
                    "id": row["id"],
                    "role": row["role"],
                    "content": content,
                    "turn_index": row["turn_index"],
                    "created_at": row["created_at"],
                }
            )
        return messages

    def delete_messages(self, conversation_id: str, message_ids: Sequence[int]) -> int:
        if not message_ids:
            return 0
        placeholders = ",".join(["?"] * len(message_ids))
        params: list[Any] = [conversation_id]
        params.extend(message_ids)
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"DELETE FROM messages WHERE conversation_id=? AND id IN ({placeholders})",
                params,
            )
            return cur.rowcount

    def save_compaction_state(self, conversation_id: str, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload)
        updated_at = int(time.time())
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO compaction_state (conversation_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (conversation_id, encoded, updated_at),
            )

    def get_compaction_state(self, conversation_id: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT payload_json FROM compaction_state WHERE conversation_id=?",
            (conversation_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return None

    def get_response_record(self, response_id: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            """
            SELECT id,
                   conversation_id,
                   parent_response_id,
                   model,
                   instructions,
                   input_json,
                   output_json,
                   last_message_turn
            FROM responses
            WHERE id=?""",
            (response_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        record = dict(row)
        return record

    def get_history_for_response(self, response_id: str) -> list[dict[str, Any]]:
        record = self.get_response_record(response_id)
        if not record:
            return []

        conversation_id = record["conversation_id"]
        last_turn = record["last_message_turn"]
        return self.get_messages(conversation_id, up_to_turn=last_turn)


class ContextWindowManager:
    """Sliding window helper enforcing a token budget."""

    def __init__(self, token_budget: int | None = 16384) -> None:
        self.token_budget = token_budget

    def estimate_tokens(
        self,
        messages: Sequence[dict[str, Any]],
        tokenizer: Any,
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> int | None:
        if not messages:
            return 0
        if tokenizer is None:
            return None
        try:
            tokens = tokenizer.apply_chat_template(
                list(messages),
                tools=list(tools) if tools else None,
                add_generation_prompt=True,
                tokenize=True,
            )
            if isinstance(tokens, dict) and "input_ids" in tokens:
                return len(tokens["input_ids"])
            if isinstance(tokens, (list, tuple)):
                return len(tokens)
        except Exception:  # pragma: no cover - tokenizer specific
            return None
        return None

    def trim(
        self,
        messages: Sequence[dict[str, Any]],
        tokenizer: Any,
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if not messages:
            return []
        if self.token_budget is None or self.token_budget <= 0:
            return list(messages)

        trimmed = list(messages)

        count = self.estimate_tokens(trimmed, tokenizer, tools)
        if count is None or count <= self.token_budget:
            return trimmed

        # Sliding window: drop earliest message until within budget.
        while len(trimmed) > 1:
            trimmed = trimmed[1:]
            count = self.estimate_tokens(trimmed, tokenizer, tools)
            if count is not None and count <= self.token_budget:
                break

        return trimmed


__all__ = ["ConversationStore", "ContextWindowManager"]
