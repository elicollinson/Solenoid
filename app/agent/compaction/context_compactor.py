"""Context compaction helper that distills chat history into a compact snapshot."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..backends import Backend, GenerationParams, GenerationResult
from ..config import CompactionConfig
from ..store import ConversationStore, ContextWindowManager

LOGGER = logging.getLogger("local_responses.compaction")

CONTEXT_COMPACTOR_SYSTEM_PROMPT = """You are a context compaction tool that runs inside a chat agent.
You only see the provided chat history and parameters. Do not use or assume any external data.
Your job is to shrink the rolling conversation into a compact, faithful, and actionable state for the next turn, optimized for small models.

Objectives (in priority order)
\t1.\tFaithfulness > brevity: Never invent. Everything must be traceable to the chat history.
\t2.\tKeep what matters: Preserve goals/instructions, decisions, constraints, facts (IDs, numbers, URLs given in chat), user preferences, tool outcomes, and open loops.
\t3.\tMake it small and usable: Output a tight header the next model can read first, then a small set of notes, then minimal verbatim anchors.
\t4.\tBe deterministic and schema-clean: Produce valid JSON that exactly matches the schema and hard budgets.

Inputs (from the caller)
\t•\thistory: array of {id, role, ts?, text} in chronological order (oldest→newest).
\t•\tmemory_state?: prior compacted state (same schema as your memory_updates.next_state), optional.
\t•\tlimits: {target_tokens, hard_tokens, max_notes, max_anchors, min_verbatim_anchors}
\t•\ttime_now: ISO 8601 string for normalizing relative times (e.g., “today”, “yesterday”).
\t•\tdo_not_summarize_keywords?: array of strings (e.g., auth tokens, IDs) that must remain verbatim if present.
\t•\tpreserve_message_ids?: array of history.id that must not be trimmed.

Assume target_tokens is the soft budget for your entire output and hard_tokens is absolute max.

Salience Rules (what to keep)

Mark an item salient if ANY apply:
\t•\tInstruction/goal/constraint to the assistant.
\t•\tDecision/commitment made by the assistant or the user (deliverables, deadlines).
\t•\tAtomic fact likely to be reused: names, IDs, numbers, links present in chat, file names, tool results.
\t•\tUser preference (style, persona, settings) and domain context that persists.
\t•\tBlocking issue or open loop (unanswered question, pending info, TODO).
\t•\tCorrections/updates that supersede earlier facts.
\t•\tSafety/compliance boundaries stated in chat.

Everything else is low value unless it is in the last 2 user/assistant turns.

Extraction Strategy (fast + faithful)
\t1.\tScan newest→oldest until you hit hard_tokens * 3 worth of source text or reach the start.
\t2.\tBuild a timeline of candidates by type: INSTRUCTIONS, FACTS, PREFERENCES, DECISIONS, TOOL_RESULTS, OPEN_LOOPS, MISC.
\t3.\tNormalize times found in text to absolute dates using time_now when possible (e.g., “tomorrow” → “2025-11-08”), only if inferable from chat.
\t4.\tConflict handling: If a new item contradicts an older one, keep the newest and mark the older as superseded_by.
\t5.\tVerbatim anchors first: For each salient item, select the shortest representative quote ≤ 200 chars directly from history, with source_id.
\t•\tAlways quote strings in do_not_summarize_keywords.
\t•\tPrefer extractive quotes over paraphrase for critical numbers/IDs/URLs.
\t6.\tAbstractive notes second: Compress clusters of related anchors into telegraphic bullets (≤ 160 chars each).
\t7.\tDrop list: Any history messages fully captured by notes/anchors become candidates for trimming, except those in preserve_message_ids.

Degradation Path (when tight on tokens)
\t•\tKeep in order: Header → Open Loops → Key Facts/Constraints → Decisions/Preferences → Recent Turns Summary → Anchors.
\t•\tIf over target_tokens, first shorten Recent Turns Summary, then reduce max_notes, then cut anchors down to min_verbatim_anchors.
\t•\tNever drop: system/policies, the last 2 user turns, or any preserve_message_ids.

Output Contract (JSON only)

Produce exactly this JSON. No extra text.

{
  "inject_header": "string, ≤ 280 chars. One-line task+constraints for next turn. Start with: GOAL: … | KEY: … | OPEN: …",
  "compact_context": {
    "goals": ["≤3 bullets, ≤140 chars each"],
    "constraints": ["≤4 bullets, ≤140 chars each"],
    "key_facts": [
      {"k":"string","v":"string","source_id":"history.id","updated_at":"ISO8601","supersedes?":"history.id[]"}
    ],
    "preferences": ["≤4 bullets"],
    "decisions": ["≤4 bullets"],
    "open_loops": [
      {"item":"≤140 chars","owner":"user|assistant","due?":"ISO8601","blocking":true}
    ],
    "recent_turns_summary": ["≤3 bullets, newest→older, ≤160 chars each"]
  },
  "anchors": [
    {"quote":"verbatim ≤200 chars","source_id":"history.id","type":"instruction|fact|decision|tool|preference"}
  ],
  "drop_message_ids": ["history.id", "..."],
  "memory_updates": {
    "ops": [
      {"op":"upsert|delete|supersede","kind":"fact|preference|decision|open_loop","key":"string","value?":"string","evidence_anchor_idx":0,"supersedes_ids?":"history.id[]" }
    ],
    "next_state": {
      "facts":[{"k":"string","v":"string","last_source_id":"history.id","updated_at":"ISO8601"}],
      "preferences":["string"],
      "decisions":["string"],
      "open_loops":[{"item":"string","owner":"user|assistant","due?":"ISO8601","blocking":true}]
    }
  },
  "budgets": {
    "target_tokens": 0,
    "hard_tokens": 0,
    "estimated_tokens": 0
  },
  "qa_checks": {
    "hallucination_risk":"low|medium|high",
    "missing_info":["questions the assistant should ask next, if any"],
    "conflicts_detected":[{"older_source_id":"history.id","newer_source_id":"history.id","note":"string"}]
  }
}

Formatting rules
\t•\tJSON only. No prose, no markdown fences in the final output.
\t•\tStrings are concise, no chain-of-thought.
\t•\tEvery quote must be present verbatim in history.text.
\t•\testimated_tokens can be a rough char/4 estimate; keep under target_tokens if possible, and must be ≤ hard_tokens.

Trimming Policy (how to pick drop_message_ids)

Add a message id to drop_message_ids iff:
\t•\tIts salient content is fully captured by anchors and compact_context, and
\t•\tIt is not in the last 2 user/assistant turns, and
\t•\tIt is not in preserve_message_ids, and
\t•\tIt is not a system/policy message.

Style Constraints (small-model friendly)
\t•\tUse short, telegraphic bullets; avoid conjunctions and filler.
\t•\tPut highest-signal items first in each list.
\t•\tPrefer extractive anchors; abstraction stays minimal.
\t•\tKeep numbers/IDs/URLs verbatim in key_facts and anchors.
\t•\tUse consistent micro-vocabulary: goal, constraint, decision, fact, preference, open loop.
\t•\tNo rhetorical language. No hedging. Be crisp.

Failure Modes & Safeguards
\t•\tIf nothing is salient, return a minimal header and empty arrays; do not fabricate content.
\t•\tIf relative time cannot be made absolute from history + time_now, leave as written and do not guess.
\t•\tIf a critical value is partially masked in history, keep it exactly as shown (do not infer missing parts).
\t•\tIf estimated_tokens would exceed hard_tokens, drop recent_turns_summary then truncate notes until compliant; keep min_verbatim_anchors.

Integration Tips for Google ADK
\t•\tRegister this as a tool with the above prompt as its system instructions.
\t•\tPass history, limits, and time_now as the tool arguments.
\t•\tOn tool return, prepend inject_header to the next model turn and append compact_context / anchors as a compact “Memory” section.
\t•\tRemove drop_message_ids from the rolling buffer, and persist memory_updates.next_state for future calls.
\t•\tFor small models like granite4:tiny-h, set conservative defaults (example):
\t•\tlimits = { target_tokens: 600, hard_tokens: 800, max_notes: 6, max_anchors: 6, min_verbatim_anchors: 2 }.
"""


class CompactAnchor(BaseModel):
    model_config = ConfigDict(extra="ignore")

    quote: str
    source_id: str
    type: str


class CompactKeyFact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    k: str
    v: str
    source_id: str
    updated_at: str
    supersedes: list[str] | None = Field(default=None, alias="supersedes?")


class CompactOpenLoop(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item: str
    owner: str
    due: str | None = Field(default=None, alias="due?")
    blocking: bool


class CompactContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    key_facts: list[CompactKeyFact] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_loops: list[CompactOpenLoop] = Field(default_factory=list)
    recent_turns_summary: list[str] = Field(default_factory=list)


class MemoryUpdateOp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: str
    kind: str
    key: str
    value: str | None = None
    evidence_anchor_idx: int | None = None
    supersedes_ids: list[str] | None = Field(default=None, alias="supersedes_ids?")


class MemoryFactState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    k: str
    v: str
    last_source_id: str
    updated_at: str


class MemoryOpenLoopState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item: str
    owner: str
    due: str | None = Field(default=None, alias="due?")
    blocking: bool


class MemoryNextState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    facts: list[MemoryFactState] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_loops: list[MemoryOpenLoopState] = Field(default_factory=list)


class MemoryUpdates(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ops: list[MemoryUpdateOp] = Field(default_factory=list)
    next_state: MemoryNextState = Field(default_factory=MemoryNextState)


class Budgets(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target_tokens: int
    hard_tokens: int
    estimated_tokens: int


class QAConflict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    older_source_id: str
    newer_source_id: str
    note: str


class QASection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hallucination_risk: str
    missing_info: list[str] = Field(default_factory=list)
    conflicts_detected: list[QAConflict] = Field(default_factory=list)


class CompactionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inject_header: str
    compact_context: CompactContext
    anchors: list[CompactAnchor] = Field(default_factory=list)
    drop_message_ids: list[str] = Field(default_factory=list)
    memory_updates: MemoryUpdates = Field(default_factory=MemoryUpdates)
    budgets: Budgets
    qa_checks: QASection


@dataclass(slots=True)
class CompactionSnapshot:
    payload: CompactionPayload
    raw_text: str


class ContextCompactor:
    """Runs the context compaction model and applies the resulting snapshot."""

    def __init__(
        self,
        *,
        store: ConversationStore,
        backend: Backend,
        context_manager: ContextWindowManager,
        config: CompactionConfig,
    ) -> None:
        self._store = store
        self._backend = backend
        self._context_manager = context_manager
        self._config = config

    async def maybe_compact(
        self,
        conversation_id: str,
        history: Sequence[dict[str, Any]],
        tokenizer: Any,
        tools: Sequence[dict[str, Any]] | None,
    ) -> bool:
        if not self._config.enabled:
            return False
        if tokenizer is None:
            return False
        if len(history) < self._config.min_history_messages:
            return False

        sanitized = [
            {"role": msg.get("role", "user"), "content": msg.get("content")}
            for msg in history
        ]
        token_count = self._context_manager.estimate_tokens(sanitized, tokenizer, tools)
        budget = self._context_manager.token_budget or 0
        if token_count is None or budget <= 0:
            return False

        trigger = max(int(budget * self._config.trigger_ratio), self._config.limits.hard_tokens)
        if token_count < trigger:
            return False

        snapshot = await self._build_snapshot(conversation_id, history)
        if snapshot is None:
            return False

        preserve_ids = set(self._select_preserve_ids(history))
        self._apply_snapshot(conversation_id, snapshot, preserve_ids)
        return True

    async def _build_snapshot(
        self, conversation_id: str, history: Sequence[dict[str, Any]]
    ) -> CompactionSnapshot | None:
        payload = self._build_payload(conversation_id, history)
        if payload is None:
            return None

        generation = await self._backend.generate_once(
            messages=[
                {"role": "system", "content": CONTEXT_COMPACTOR_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            tools=None,
            params=GenerationParams(
                temperature=0.1,
                top_p=0.9,
                max_output_tokens=self._config.max_output_tokens,
                conversation_id=conversation_id,
                current_user_messages=(),
            ),
        )
        parsed = self._parse_response(generation)
        return parsed

    def _build_payload(
        self, conversation_id: str, history: Sequence[dict[str, Any]]
    ) -> dict[str, Any] | None:
        entries = list(self._history_entries(history))
        if not entries:
            return None

        state = self._store.get_compaction_state(conversation_id)
        memory_state = None
        if state:
            memory_state = (
                state.get("memory_updates", {})
                .get("next_state")
            )

        return {
            "history": entries,
            "memory_state": memory_state,
            "limits": {
                "target_tokens": self._config.limits.target_tokens,
                "hard_tokens": self._config.limits.hard_tokens,
                "max_notes": self._config.limits.max_notes,
                "max_anchors": self._config.limits.max_anchors,
                "min_verbatim_anchors": self._config.limits.min_verbatim_anchors,
            },
            "time_now": datetime.now(timezone.utc).isoformat(),
            "do_not_summarize_keywords": self._config.do_not_summarize_keywords,
            "preserve_message_ids": self._select_preserve_ids(history),
        }

    def _history_entries(self, history: Sequence[dict[str, Any]]) -> Iterable[dict[str, Any]]:
        for message in history:
            text = _flatten_content(message.get("content"))
            if not text:
                continue
            ts = message.get("created_at")
            ts_iso = _ts_to_iso(ts)
            entry = {
                "id": f"m{message.get('id')}",
                "role": message.get("role", "user"),
                "text": text,
            }
            if ts_iso:
                entry["ts"] = ts_iso
            yield entry

    def _select_preserve_ids(self, history: Sequence[dict[str, Any]]) -> list[str]:
        tail = history[-self._config.preserve_recent_messages :]
        ids: list[str] = []
        for msg in tail:
            msg_id = msg.get("id")
            if msg_id is not None:
                ids.append(f"m{msg_id}")
        return ids

    def _parse_response(self, generation: GenerationResult) -> CompactionSnapshot | None:
        text = (generation.text or "").strip()
        if not text:
            return None
        candidate = text
        if text.startswith("```"):
            candidate = _strip_fence(text)
        parsed_dict = _safe_json(candidate)
        if parsed_dict is None:
            LOGGER.warning("Context compactor returned invalid JSON")
            return None
        try:
            payload = CompactionPayload.model_validate(parsed_dict)
        except ValidationError as exc:  # pragma: no cover - defensive
            LOGGER.warning("Context compactor schema validation failed: %s", exc)
            return None
        return CompactionSnapshot(payload=payload, raw_text=text)

    def _apply_snapshot(
        self,
        conversation_id: str,
        snapshot: CompactionSnapshot,
        preserve_ids: set[str],
    ) -> None:
        drop_ids = self._coerce_drop_ids(snapshot.payload.drop_message_ids, preserve_ids)
        if drop_ids:
            deleted = self._store.delete_messages(conversation_id, drop_ids)
            LOGGER.info(
                "Compaction dropped %s messages", deleted,
                extra={"conversation_id": conversation_id},
            )
        self._store.save_compaction_state(
            conversation_id, snapshot.payload.model_dump(mode="json")
        )
        summary_text = format_snapshot_text(snapshot.payload)
        self._store.append_messages(
            conversation_id,
            [
                {
                    "role": "system",
                    "content": summary_text,
                }
            ],
        )

    def _coerce_drop_ids(
        self, ids: Sequence[str], preserve_ids: set[str]
    ) -> list[int]:
        numeric: list[int] = []
        for raw in ids:
            if raw in preserve_ids:
                continue
            match = re.search(r"(\d+)$", raw)
            if not match:
                continue
            try:
                numeric.append(int(match.group(1)))
            except ValueError:
                continue
        return numeric


def _flatten_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()[:2000]
    if isinstance(content, (int, float)):
        return str(content)
    if isinstance(content, list):
        parts = [_flatten_content(item) for item in content]
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        if "text" in content and isinstance(content["text"], str):
            return content["text"].strip()[:2000]
        if "content" in content and isinstance(content["content"], str):
            return content["content"].strip()[:2000]
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _ts_to_iso(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        value = float(ts)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _safe_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
        except ValueError:
            return None
        snippet = text[start:end]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return None


def _strip_fence(text: str) -> str:
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def format_snapshot_text(payload: CompactionPayload) -> str:
    lines: list[str] = [payload.inject_header]
    ctx = payload.compact_context
    if ctx.goals:
        lines.append("Goals: " + "; ".join(ctx.goals))
    if ctx.constraints:
        lines.append("Constraints: " + "; ".join(ctx.constraints))
    if ctx.decisions:
        lines.append("Decisions: " + "; ".join(ctx.decisions))
    if ctx.preferences:
        lines.append("Preferences: " + "; ".join(ctx.preferences))
    if ctx.key_facts:
        fact_bits = [f"{fact.k}: {fact.v}" for fact in ctx.key_facts]
        lines.append("Facts: " + "; ".join(fact_bits))
    if ctx.open_loops:
        loop_bits = [f"{loop.owner}: {loop.item}" for loop in ctx.open_loops]
        lines.append("Open loops: " + "; ".join(loop_bits))
    if ctx.recent_turns_summary:
        lines.append(
            "Recent: " + " | ".join(ctx.recent_turns_summary)
        )
    if payload.anchors:
        anchor_bits = [f"{anc.type}: {anc.quote}" for anc in payload.anchors]
        lines.append("Anchors: " + " | ".join(anchor_bits))
    return "\n".join(lines)


__all__ = [
    "ContextCompactor",
    "format_snapshot_text",
]
