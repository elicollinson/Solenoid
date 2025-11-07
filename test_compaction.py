from __future__ import annotations

import json
import asyncio
from pathlib import Path

from local_responses.compaction.context_compactor import ContextCompactor
from local_responses.config import CompactionConfig, CompactionLimitsConfig
from local_responses.store import ConversationStore, ContextWindowManager
from local_responses.backends import GenerationResult


class _StubBackend:
    def __init__(self, text: str) -> None:
        self._text = text

    async def ensure_ready(self) -> None:  # pragma: no cover - unused
        return None

    def supports_json_schema(self) -> bool:  # pragma: no cover - unused
        return False

    async def generate_stream(self, messages, tools, params):  # pragma: no cover - unused
        raise NotImplementedError

    async def generate_once(self, messages, tools, params):
        return GenerationResult(text=self._text)


class _StubTokenizer:
    def apply_chat_template(self, messages, tools=None, add_generation_prompt=True, tokenize=False):
        if tokenize:
            total = sum(len(str(msg.get("content", ""))) for msg in messages)
            total = max(total, 1)
            return {"input_ids": list(range(total))}
        return "".join(str(msg.get("content", "")) for msg in messages)


def test_context_compactor_applies_snapshot(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "compaction.db")
    conversation_id = store.ensure_conversation()
    store.append_messages(
        conversation_id,
        [
            {"role": "user", "content": "Need summary"},
            {"role": "assistant", "content": "Working on it"},
            {"role": "user", "content": "Please remember the repo url"},
        ],
    )
    history = store.get_messages(conversation_id)

    payload = {
        "inject_header": "GOAL: Keep repo handy | KEY: repo url | OPEN: none",
        "compact_context": {
            "goals": ["Remember repo details"],
            "constraints": [],
            "key_facts": [
                {
                    "k": "repo",
                    "v": "general_local_agent",
                    "source_id": "m1",
                    "updated_at": "2025-01-01T00:00:00Z",
                }
            ],
            "preferences": [],
            "decisions": [],
            "open_loops": [],
            "recent_turns_summary": ["User stressed repo url"],
        },
        "anchors": [
            {"quote": "\"Please remember the repo url\"", "source_id": "m3", "type": "fact"}
        ],
        "drop_message_ids": ["m1"],
        "memory_updates": {
            "ops": [
                {
                    "op": "upsert",
                    "kind": "fact",
                    "key": "repo",
                    "value": "general_local_agent",
                    "evidence_anchor_idx": 0,
                }
            ],
            "next_state": {
                "facts": [
                    {
                        "k": "repo",
                        "v": "general_local_agent",
                        "last_source_id": "m3",
                        "updated_at": "2025-01-01T00:00:00Z",
                    }
                ],
                "preferences": [],
                "decisions": [],
                "open_loops": [],
            },
        },
        "budgets": {"target_tokens": 600, "hard_tokens": 800, "estimated_tokens": 120},
        "qa_checks": {
            "hallucination_risk": "low",
            "missing_info": [],
            "conflicts_detected": [],
        },
    }

    backend = _StubBackend(json.dumps(payload))
    limits = CompactionLimitsConfig(target_tokens=100, hard_tokens=5, max_notes=4, max_anchors=4, min_verbatim_anchors=1)
    config = CompactionConfig(
        enabled=True,
        trigger_ratio=0.1,
        min_history_messages=2,
        preserve_recent_messages=1,
        max_output_tokens=256,
        limits=limits,
    )
    manager = ContextWindowManager(token_budget=10)
    compactor = ContextCompactor(
        store=store,
        backend=backend,
        context_manager=manager,
        config=config,
    )

    tokenizer = _StubTokenizer()
    mutated = asyncio.run(
        compactor.maybe_compact(conversation_id, history, tokenizer, tools=None)
    )
    assert mutated is True

    state = store.get_compaction_state(conversation_id)
    assert state is not None
    assert state["compact_context"]["goals"] == ["Remember repo details"]

    updated_history = store.get_messages(conversation_id)
    assert any(msg["role"] == "system" and "GOAL:" in str(msg["content"]) for msg in updated_history)

    dropped_ids = {msg["id"] for msg in updated_history}
    assert 1 not in dropped_ids

    store.close()
