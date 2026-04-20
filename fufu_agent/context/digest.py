"""Conversation-driven relationship digest: chat history → LLM signals → L1/L0 updates."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from ..events import EventBus
from ..llm.adapter import LLMAdapter, default_llm_adapter
from ..models import (
    ChatDigestState,
    ChatHistoryEntry,
    EvolutionLogEntry,
    Personality,
    Rhythm,
    Soul,
)
from ..storage import FileStore, default_file_store

logger = logging.getLogger(__name__)

CHAT_HISTORY_FILE = "chat_history.jsonl"
DIGEST_STATE_FILE = "chat_digest_state.json"
MAX_BATCH_ENTRIES = 80


def _format_pending_messages(entries: list[ChatHistoryEntry]) -> str:
    lines: list[str] = []
    for e in entries:
        label = "用户" if e.role == "user" else "陪伴"
        lines.append(f"[{label}] {e.content}")
    return "\n".join(lines)


def _clamp_delta(raw) -> float:
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(-0.1, min(0.1, x))


class RelationshipDigester:
    def __init__(
        self,
        *,
        file_store: Optional[FileStore] = None,
        llm_adapter: Optional[LLMAdapter] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.file_store = file_store or default_file_store
        self.llm = llm_adapter or default_llm_adapter
        self.event_bus = event_bus or EventBus()

    async def run_digest(self, *, manual: bool = False) -> dict:
        """
        manual=True：至少 2 条待处理消息即可整理（方便 Demo）；自动调度为 4 条。
        成功消费一批对话后 notify_scheduler=True，由调用方执行 scheduler.mark_digested()。
        """
        min_pending = 2 if manual else 4
        checkpoint = self.file_store.load(DIGEST_STATE_FILE, ChatDigestState)
        if not checkpoint:
            checkpoint = ChatDigestState()

        all_entries = self.file_store.read_jsonl(
            CHAT_HISTORY_FILE, ChatHistoryEntry
        )
        total = len(all_entries)
        if checkpoint.processed_lines > total:
            checkpoint.processed_lines = 0

        pending = all_entries[checkpoint.processed_lines:]
        if len(pending) < min_pending:
            return {
                "ok": True,
                "skipped": True,
                "reason": f"待整理消息不足 {min_pending} 条（当前新增 {len(pending)} 条）",
                "notify_scheduler": False,
            }

        batch = pending[:MAX_BATCH_ENTRIES]

        personality = self.file_store.load("personality.json", Personality)
        if not personality:
            return {
                "ok": False,
                "error": "personality.json 不存在",
                "notify_scheduler": False,
            }

        if not self.llm.available:
            return {
                "ok": False,
                "error": "LLM 未配置",
                "notify_scheduler": False,
            }

        messages_text = _format_pending_messages(batch)
        current_params = personality.params.model_dump(mode="json")
        result = await self.llm.digest_conversation(messages_text, current_params)
        if not result:
            return {
                "ok": False,
                "error": "模型未返回可解析的 JSON",
                "notify_scheduler": False,
            }

        rhythm = self.file_store.load("rhythm.json", Rhythm)
        soul = self.file_store.load("soul.json", Soul)

        personality_changed = self._apply_personality_deltas(personality, rhythm, result)
        soul_changed = False
        if soul:
            soul_changed = self._merge_user_snapshot(
                soul, result.get("user_snapshot") or {}
            )

        if personality_changed:
            try:
                personality.natural_description = await self.llm.generate_natural_description(
                    personality.model_dump(mode="json")
                )
            except Exception as e:
                logger.warning("Natural description refresh failed: %s", e)
            personality.updated_at = datetime.now()
            self.file_store.save("personality.json", personality)
            await self.event_bus.publish(
                "personality_update",
                {
                    "version": personality.version,
                    "params": personality.params.model_dump(),
                    "natural_description": personality.natural_description,
                    "voice_style": personality.voice_style,
                },
            )

        if soul_changed and soul:
            self.file_store.save("soul.json", soul)
            await self.event_bus.publish(
                "soul_update", {"soul": soul.model_dump(mode="json")}
            )

        checkpoint.processed_lines += len(batch)
        self.file_store.save(DIGEST_STATE_FILE, checkpoint)

        return {
            "ok": True,
            "skipped": False,
            "notify_scheduler": True,
            "personality_changed": personality_changed,
            "soul_changed": soul_changed,
            "processed_batch": len(batch),
            "digest": result,
        }

    def _apply_personality_deltas(
        self, personality: Personality, rhythm: Rhythm | None, result: dict
    ) -> bool:
        p = personality.params
        changed = False
        pa = result.get("personality_adjustment") or {}
        rel = result.get("relationship") or {}

        for field, key in [
            ("night_owl_index", "night_owl_delta"),
            ("anxiety_sensitivity", "anxiety_delta"),
            ("quietness", "quietness_delta"),
            ("playfulness", "playfulness_delta"),
        ]:
            d = _clamp_delta(pa.get(key, 0))
            if abs(d) < 1e-6:
                continue
            old = getattr(p, field)
            new_v = max(0.0, min(1.0, round(old + d, 3)))
            if abs(new_v - old) > 1e-6:
                setattr(p, field, new_v)
                changed = True

        attach_delta = _clamp_delta(pa.get("attachment_delta", 0)) + _clamp_delta(
            rel.get("closeness_delta", 0)
        )
        attach_delta = max(-0.1, min(0.1, attach_delta))
        if abs(attach_delta) > 1e-6:
            old = p.attachment_level
            new_v = max(0.0, min(1.0, round(old + attach_delta, 3)))
            if abs(new_v - old) > 1e-6:
                p.attachment_level = new_v
                changed = True

        if changed:
            personality.version += 1
            reason = (pa.get("reason") or "").strip() or (rel.get("signals") or "").strip()
            if len(reason) > 200:
                reason = reason[:200] + "…"
            personality.evolution_log.append(
                EvolutionLogEntry(
                    day=rhythm.days_together if rhythm else 0,
                    change=(
                        f"digest: owl={p.night_owl_index}, anx={p.anxiety_sensitivity}, "
                        f"quiet={p.quietness}, play={p.playfulness}, attach={p.attachment_level}"
                    ),
                    reason=f"conversation_digest: {reason or '对话整理'}",
                    timestamp=datetime.now(),
                )
            )
        return changed

    def _merge_user_snapshot(self, soul: Soul, snap: dict) -> bool:
        changed = False
        w = snap.get("current_state_word")
        if isinstance(w, str) and w.strip():
            soul.current_state_word = w.strip()
            changed = True
        s = snap.get("struggle")
        if isinstance(s, str) and s.strip():
            soul.struggle = s.strip()
            changed = True
        facts = snap.get("facts")
        if isinstance(facts, str) and facts.strip():
            f = facts.strip()
            existing = (soul.user_facts or "").strip()
            if not existing:
                soul.user_facts = f
                changed = True
            elif f not in existing:
                soul.user_facts = f"{existing}；{f}"
                changed = True
        return changed


default_relationship_digester = RelationshipDigester()


__all__ = ["RelationshipDigester", "default_relationship_digester"]
