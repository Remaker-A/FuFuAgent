"""``CompanionAgent`` — FuFuAgent 的门面类。

把状态机、LLM 适配器、上下文管理、性格演化、对话整理和调度器组装成一个完整
agent。外部 app（FastAPI、WebSocket、桌面应用、CLI）只需要面对这一个对象即可。

每个 ``CompanionAgent`` 实例都拥有自己独立的组件（不会污染模块级默认单例），
因此同一进程里可以并存多个 agent——比如一个生产实例 + 一个测试实例。
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import AgentConfig, default_config
from .context.digest import RelationshipDigester
from .context.manager import ContextManager
from .core.personality_engine import PersonalityEngine
from .core.scheduler import Scheduler
from .core.state_machine import StateMachine
from .events import EventBus, EventHandler
from .llm.adapter import LLMAdapter
from .llm.corpus import Corpus
from .llm.presets import get_preset
from .llm.prompts import format_context_markdown_snapshot
from .models import (
    BiasType,
    ChatHistoryEntry,
    CompanionState,
    Note,
    Personality,
    PersonalityParams,
    Rhythm,
    Soul,
    SoulCreateRequest,
    StateEvent,
    UserMessage,
)
from .storage import FileStore

logger = logging.getLogger(__name__)


class SoulAlreadyExists(RuntimeError):
    """尝试创建 Soul，但 ``soul.json`` 已经存在。"""


class SoulNotInitialized(RuntimeError):
    """调用需要 Soul/Personality 的接口，但尚未创建。"""


class CompanionAgent:
    """整合所有子系统的 agent 门面。"""

    # 创建 Soul 时清空的文件集合
    _RESET_FILES = (
        "soul.json",
        "personality.json",
        "rhythm.json",
        "events.jsonl",
        "notes.json",
        "messages.jsonl",
        "chat_history.jsonl",
        "chat_digest_state.json",
    )

    def __init__(
        self,
        *,
        config: Optional[AgentConfig] = None,
        data_dir: Optional[Path] = None,
        event_bus: Optional[EventBus] = None,
        auto_record_chat: bool = True,
    ) -> None:
        self.config = config or default_config
        if data_dir is not None:
            new_data_dir = Path(data_dir).expanduser().resolve()
            new_corpus_dir = new_data_dir / "corpus"
            new_data_dir.mkdir(parents=True, exist_ok=True)
            new_corpus_dir.mkdir(parents=True, exist_ok=True)
            self.config = self.config.model_copy(
                update={"data_dir": new_data_dir, "corpus_dir": new_corpus_dir}
            )

        self.event_bus = event_bus or EventBus()
        self.auto_record_chat = auto_record_chat

        # 核心组件：全部使用注入好的 config 自成一套
        self.file_store = FileStore(config=self.config)
        self.corpus = Corpus(config=self.config)
        self.llm_adapter = LLMAdapter(config=self.config, corpus=self.corpus)
        self.state_machine = StateMachine(config=self.config)
        self.context_manager = ContextManager(
            file_store=self.file_store,
            state_machine=self.state_machine,
        )
        self.digester = RelationshipDigester(
            file_store=self.file_store,
            llm_adapter=self.llm_adapter,
            event_bus=self.event_bus,
        )
        self.personality_engine = PersonalityEngine(
            file_store=self.file_store,
            llm_adapter=self.llm_adapter,
            event_bus=self.event_bus,
            context_manager=self.context_manager,
        )
        self.scheduler = Scheduler(
            config=self.config,
            on_digest_due=self._scheduled_digest,
            on_evolve_due=self._scheduled_evolve,
        )

        # state_machine -> event_bus 桥接
        self.state_machine.on_state_change(self._state_change_bridge)

        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动后台调度循环。"""
        if self._started:
            return
        await self.scheduler.start()
        self._started = True

    async def stop(self) -> None:
        """停止调度 + 关闭 LLM HTTP client。"""
        await self.scheduler.stop()
        await self.llm_adapter.close()
        self._started = False

    async def __aenter__(self) -> "CompanionAgent":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Event subscription shortcuts
    # ------------------------------------------------------------------

    def subscribe(self, handler: EventHandler) -> EventHandler:
        """订阅所有事件。``handler(event_type, data)`` 支持 sync / async。"""
        return self.event_bus.subscribe(handler)

    def on(self, event_type: str, handler):
        """订阅单一事件类型。"""
        async def _filtered(t: str, d: dict):
            if t == event_type:
                result = handler(d)
                if hasattr(result, "__await__"):
                    await result
        return self.event_bus.subscribe(_filtered)

    # ------------------------------------------------------------------
    # Soul / Personality lifecycle
    # ------------------------------------------------------------------

    def create_soul(self, req: SoulCreateRequest) -> Soul:
        """按请求创建 Soul + 初始 Personality。"""
        if self.file_store.exists("soul.json"):
            raise SoulAlreadyExists("soul.json 已存在；请先 reset()")

        voice_style = self._resolve_voice_style(req)
        params = self._build_personality_params(req.bias)

        soul = Soul(
            created_at=datetime.now(),
            current_state_word=req.current_state_word,
            struggle=req.struggle,
            bias=req.bias,
            opening_response="你来了。",
        )
        self.file_store.save("soul.json", soul)

        personality = Personality(
            version=1,
            updated_at=datetime.now(),
            params=params,
            natural_description=self._initial_description(req.bias),
            voice_style=voice_style,
            evolution_log=[],
        )
        self.file_store.save("personality.json", personality)
        return soul

    def get_soul(self) -> Optional[Soul]:
        return self.file_store.load("soul.json", Soul)

    def get_personality(self) -> Optional[Personality]:
        return self.file_store.load("personality.json", Personality)

    def get_rhythm(self) -> Optional[Rhythm]:
        return self.file_store.load("rhythm.json", Rhythm)

    def save_rhythm(self, rhythm: Rhythm) -> None:
        self.file_store.save("rhythm.json", rhythm)

    def reset(self) -> None:
        """清空 Soul 及所有相关运行数据（开发期用）。"""
        for fname in self._RESET_FILES:
            path = self.file_store.data_dir / fname
            if path.exists():
                os.remove(path)

    # ------------------------------------------------------------------
    # Conversational APIs
    # ------------------------------------------------------------------

    async def say_one_line(self) -> str:
        """生成一句 ≤15 字的陪伴短语。"""
        ctx = self.context_manager.for_say_one_line()
        return await self.llm_adapter.generate_say_one_line(ctx)

    async def chat(
        self,
        message: str,
        history: Optional[list[dict]] = None,
        *,
        record: Optional[bool] = None,
    ) -> str:
        """多轮对话。

        ``history`` 为 ``[{role, content}, ...]`` 列表（不含当前 ``message``）。
        默认会把 (user, assistant) 两条追加到 ``chat_history.jsonl`` 并通知 scheduler；
        想纯做一次性 inference 时传 ``record=False``。
        """
        if not message or not message.strip():
            raise ValueError("message 不能为空")
        if not self.llm_adapter.available:
            raise RuntimeError("LLM 未配置（检查 SILICONFLOW_API_KEY 等）")

        ctx = self.context_manager.for_chat()
        reply = await self.llm_adapter.generate_chat_reply(
            ctx, history or [], message
        )

        should_record = self.auto_record_chat if record is None else record
        if should_record and reply:
            try:
                self.file_store.append_jsonl(
                    "chat_history.jsonl",
                    ChatHistoryEntry(
                        role="user", content=message.strip(), timestamp=datetime.now()
                    ),
                )
                self.file_store.append_jsonl(
                    "chat_history.jsonl",
                    ChatHistoryEntry(
                        role="assistant",
                        content=reply.strip(),
                        timestamp=datetime.now(),
                    ),
                )
                self.scheduler.record_chat_message()
            except Exception as e:
                logger.warning("chat_history append failed: %s", e)
        return reply

    async def generate_note(self) -> Note:
        """生成一条"纸条"并持久化。"""
        ctx = self.context_manager.for_note()
        content = await self.llm_adapter.generate_note(ctx)

        personality = self.get_personality()
        note = Note(
            id=str(uuid.uuid4())[:8],
            content=content,
            created_at=datetime.now(),
            personality_version=personality.version if personality else 1,
        )
        notes = self.file_store.load_json_list("notes.json", Note)
        notes.append(note)
        self.file_store.save_json_list("notes.json", notes)
        return note

    def list_notes(self) -> list[Note]:
        return self.file_store.load_json_list("notes.json", Note)

    def leave_message(self, content: str, mood: Optional[str] = None) -> None:
        msg = UserMessage(content=content, mood=mood, created_at=datetime.now())
        self.file_store.append_jsonl("messages.jsonl", msg)

    # ------------------------------------------------------------------
    # State machine shortcuts
    # ------------------------------------------------------------------

    async def person_arrive(self):
        await self.state_machine.person_arrive()

    async def person_sit(self):
        await self.state_machine.person_sit()

    async def person_leave(self):
        await self.state_machine.person_leave()

    async def start_focus(self, duration_minutes: int = 25):
        await self.state_machine.start_focus(duration_minutes)

    async def stop_focus(self):
        await self.state_machine.stop_focus()

    def get_status(self) -> dict:
        return self.state_machine.get_status()

    # ------------------------------------------------------------------
    # Evolution / digest
    # ------------------------------------------------------------------

    async def run_digest(self, *, manual: bool = False) -> dict:
        out = await self.digester.run_digest(manual=manual)
        if out.get("notify_scheduler"):
            self.scheduler.mark_digested()
        return out

    async def maybe_evolve(self) -> None:
        await self.personality_engine.maybe_evolve()
        self.scheduler.mark_evolved()

    # ------------------------------------------------------------------
    # Context inspection helpers
    # ------------------------------------------------------------------

    def assemble_context(self, levels: Optional[list[int]] = None) -> dict:
        return self.context_manager.assemble(levels or [0, 1, 2, 3])

    def export_context_markdown(self) -> str:
        ctx = self.context_manager.for_chat()
        return format_context_markdown_snapshot(ctx)

    # ------------------------------------------------------------------
    # Internal wiring
    # ------------------------------------------------------------------

    async def _state_change_bridge(self, event: StateEvent) -> None:
        """把 StateMachine 的事件转成持久化 + scheduler + event_bus 三件事。"""
        try:
            self.file_store.append_jsonl("events.jsonl", event)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("events.jsonl append failed: %s", e)
        self.scheduler.record_event()

        say_line: Optional[str] = None
        if event.to_state in (
            CompanionState.COMPANION,
            CompanionState.DEEP_NIGHT,
            CompanionState.LEAVING,
        ):
            try:
                ctx = self.context_manager.for_say_one_line()
                say_line = await self.llm_adapter.generate_say_one_line(ctx)
            except Exception:
                say_line = "嗯。"

        await self.event_bus.publish(
            "state_change",
            {
                "from": event.from_state.value,
                "to": event.to_state.value,
                "status": self.state_machine.get_status(),
                "say_line": say_line,
            },
        )

    async def _scheduled_digest(self) -> None:
        out = await self.digester.run_digest()
        if out.get("notify_scheduler"):
            self.scheduler.mark_digested()

    async def _scheduled_evolve(self) -> None:
        await self.personality_engine.maybe_evolve()
        self.scheduler.mark_evolved()

    # ------------------------------------------------------------------
    # Soul-creation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_personality_params(bias: BiasType) -> PersonalityParams:
        params = PersonalityParams(bias=bias)
        if bias == BiasType.CUSTOM:
            return params
        preset = get_preset(bias.value)
        if not preset:
            return params
        for key, val in preset.default_params.items():
            if hasattr(params, key):
                setattr(params, key, val)
        return params

    @staticmethod
    def _resolve_voice_style(req: SoulCreateRequest) -> str:
        if req.bias == BiasType.CUSTOM:
            text = (req.custom_voice_style or "").strip()
            if not text:
                raise ValueError(
                    "选择「自定义」时请填写 custom_voice_style（描述说话风格）。"
                )
            return text
        preset = get_preset(req.bias.value)
        return preset.voice_style if preset else ""

    @staticmethod
    def _initial_description(bias: BiasType) -> str:
        if bias == BiasType.CUSTOM:
            return "它刚刚来到这里，还在认识你。主人为你写下了专属的说话方式。"
        preset = get_preset(bias.value)
        if preset:
            return f"它刚刚来到这里，还在认识你。{preset.short_desc}"
        legacy = {
            BiasType.DECISIVE: "它刚刚来到这里，还在认识你。它的性格偏果断，喜欢干脆利落。",
            BiasType.ADVENTUROUS: "它刚刚来到这里，还在认识你。它的性格偏冒险，对新事物充满好奇。",
            BiasType.SLOW_DOWN: "它刚刚来到这里，还在认识你。它的性格偏沉稳，喜欢慢慢来。",
        }
        return legacy.get(bias, "它刚刚来到这里，还在认识你。")


__all__ = [
    "CompanionAgent",
    "SoulAlreadyExists",
    "SoulNotInitialized",
]
