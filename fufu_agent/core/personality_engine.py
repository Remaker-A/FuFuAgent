"""Personality evolution engine - LLM-driven with rule-based fallback."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from ..events import EventBus
from ..llm.adapter import LLMAdapter, default_llm_adapter
from ..models import (
    CompanionState,
    EvolutionLogEntry,
    Personality,
    Rhythm,
    StateEvent,
)
from ..storage import FileStore, default_file_store

if TYPE_CHECKING:
    from ..context.manager import ContextManager

logger = logging.getLogger(__name__)


class PersonalityEngine:
    def __init__(
        self,
        *,
        file_store: Optional[FileStore] = None,
        llm_adapter: Optional[LLMAdapter] = None,
        event_bus: Optional[EventBus] = None,
        context_manager: Optional["ContextManager"] = None,
    ) -> None:
        self.file_store = file_store or default_file_store
        self.llm = llm_adapter or default_llm_adapter
        self.event_bus = event_bus or EventBus()
        self._context_manager = context_manager

    def _get_context_manager(self) -> "ContextManager":
        if self._context_manager is None:
            from ..context.manager import default_context_manager
            self._context_manager = default_context_manager
        return self._context_manager

    async def maybe_evolve(self):
        personality = self.file_store.load("personality.json", Personality)
        rhythm = self.file_store.load("rhythm.json", Rhythm)
        if not personality:
            return

        events = self.file_store.read_jsonl(
            "events.jsonl", StateEvent, last_n=50
        )
        events_summary = self._summarize_events(events)

        llm_updated = await self._try_llm_evolve(personality, rhythm, events_summary)

        if not llm_updated:
            self._rule_based_evolve(personality, rhythm, events)

        personality.natural_description = await self._generate_description(personality)
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

        logger.info(
            "Personality evolved to v%s: %s", personality.version, personality.params
        )

    async def _try_llm_evolve(
        self, personality: Personality, rhythm, events_summary: str
    ) -> bool:
        try:
            if not self.llm.available:
                return False

            ctx = self._get_context_manager().for_personality_update()
            result = await self.llm.generate_personality_update(ctx, events_summary)
            if not result:
                return False

            p = personality.params
            changed = False

            for field, key in [
                ("night_owl_index", "night_owl_delta"),
                ("anxiety_sensitivity", "anxiety_delta"),
                ("quietness", "quietness_delta"),
                ("attachment_level", "attachment_delta"),
            ]:
                delta = result.get(key, 0)
                if abs(delta) > 0.001:
                    old_val = getattr(p, field)
                    new_val = max(0.0, min(1.0, round(old_val + delta, 3)))
                    setattr(p, field, new_val)
                    changed = True

            if changed:
                personality.version += 1
                personality.updated_at = datetime.now()
                personality.evolution_log.append(
                    EvolutionLogEntry(
                        day=rhythm.days_together if rhythm else 0,
                        change=(
                            f"LLM: owl={p.night_owl_index}, anx={p.anxiety_sensitivity}, "
                            f"quiet={p.quietness}, attach={p.attachment_level}"
                        ),
                        reason=result.get("reason", "LLM analysis"),
                        timestamp=datetime.now(),
                    )
                )
            return changed

        except Exception as e:
            logger.warning("LLM evolution failed, falling back to rules: %s", e)
            return False

    def _rule_based_evolve(
        self, personality: Personality, rhythm, events: list[StateEvent]
    ):
        p = personality.params
        changed = False

        if rhythm:
            if rhythm.patterns.late_night_ratio > 0.3:
                delta = min(0.05, 1.0 - p.night_owl_index)
                if delta > 0.001:
                    p.night_owl_index = round(p.night_owl_index + delta, 3)
                    changed = True

            if rhythm.patterns.regularity_score > 0.6:
                delta = min(0.03, 1.0 - p.quietness)
                if delta > 0.001:
                    p.quietness = round(p.quietness + delta, 3)
                    changed = True

            if rhythm.days_together > 0:
                delta = min(
                    0.02 * min(rhythm.days_together, 5), 1.0 - p.attachment_level
                )
                if delta > 0.001:
                    p.attachment_level = round(p.attachment_level + delta, 3)
                    changed = True

        if events:
            switch_count = len(events)
            if switch_count > 30:
                delta = min(0.03, 1.0 - p.anxiety_sensitivity)
                if delta > 0.001:
                    p.anxiety_sensitivity = round(p.anxiety_sensitivity + delta, 3)
                    changed = True

        if changed:
            personality.version += 1
            personality.updated_at = datetime.now()
            personality.evolution_log.append(
                EvolutionLogEntry(
                    day=rhythm.days_together if rhythm else 0,
                    change=(
                        f"rule: owl={p.night_owl_index}, anx={p.anxiety_sensitivity}, "
                        f"quiet={p.quietness}, attach={p.attachment_level}"
                    ),
                    reason="rule-based periodic update",
                    timestamp=datetime.now(),
                )
            )

    async def _generate_description(self, personality: Personality) -> str:
        try:
            return await self.llm.generate_natural_description(
                personality.model_dump(mode="json")
            )
        except Exception:
            return self._rule_description(personality)

    def _rule_description(self, p: Personality) -> str:
        parts = []
        bias_names = {
            "decisive": "果断",
            "adventurous": "冒险",
            "slow_down": "沉稳",
            "warm_humor": "温暖幽默",
            "night_owl": "夜猫子",
            "bookish": "爱想事情",
            "custom": "独特",
        }
        parts.append(f"它的性格偏{bias_names.get(p.params.bias.value, '果断')}")
        if p.params.night_owl_index > 0.5:
            parts.append("习惯了晚睡")
        if p.params.anxiety_sensitivity > 0.4:
            parts.append("会在你焦虑时安静一会儿")
        if p.params.attachment_level > 0.4:
            parts.append("开始认得你回来的时间了")
        if p.params.quietness > 0.6:
            parts.append("更喜欢安静地陪着")
        if p.params.playfulness > 0.55:
            parts.append("说话时会带点轻松的玩笑")
        return "，".join(parts) + "。"

    def _summarize_events(self, events: list[StateEvent]) -> str:
        if not events:
            return "最近没有事件记录。"

        state_counts: dict[str, int] = {}
        night_events = 0
        for ev in events:
            to = ev.to_state.value
            state_counts[to] = state_counts.get(to, 0) + 1
            if ev.to_state == CompanionState.DEEP_NIGHT:
                night_events += 1

        parts = [f"最近{len(events)}个事件中:"]
        for state, count in sorted(state_counts.items(), key=lambda x: -x[1]):
            parts.append(f"  进入{state}状态{count}次")
        if night_events:
            parts.append(f"  其中深夜事件{night_events}次")
        return "\n".join(parts)


default_personality_engine = PersonalityEngine()


__all__ = ["PersonalityEngine", "default_personality_engine"]
