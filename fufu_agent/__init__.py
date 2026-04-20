"""FuFuAgent — 帐篷里的陪伴型 Agent 核心库。

两种使用姿势：

1. 门面类（推荐新集成方使用）::

        from fufu_agent import CompanionAgent, SoulCreateRequest, BiasType

        agent = CompanionAgent()
        await agent.start()
        agent.create_soul(SoulCreateRequest(
            current_state_word="迷茫",
            struggle="要不要换工作",
            bias=BiasType.ADVENTUROUS,
        ))
        reply = await agent.chat("今天好累。")
        await agent.stop()

2. 模块级默认单例（和旧 backend 用法保持一致）::

        from fufu_agent import (
            default_file_store,
            default_context_manager,
            default_llm_adapter,
            default_state_machine,
        )

``default_*`` 单例共享同一份 ``default_config``，方便脚本 / 老代码直接迁移。
"""

from __future__ import annotations

from .agent import CompanionAgent, SoulAlreadyExists, SoulNotInitialized
from .config import AgentConfig, default_config
from .context.digest import RelationshipDigester, default_relationship_digester
from .context.manager import ContextManager, default_context_manager
from .core.personality_engine import PersonalityEngine, default_personality_engine
from .core.scheduler import Scheduler, default_scheduler
from .core.state_machine import StateMachine, default_state_machine
from .events import EventBus
from .llm.adapter import LLMAdapter, default_llm_adapter
from .llm.corpus import Corpus, default_corpus, pick_line
from .llm.presets import (
    PRESETS,
    PersonalityPreset,
    get_all_presets,
    get_preset,
)
from .llm.prompts import (
    build_chat_system_prompt,
    build_note_prompt,
    build_personality_update_prompt,
    build_relationship_digest_prompt,
    build_say_one_line_prompt,
    format_context_markdown_snapshot,
)
from .models import (
    BiasType,
    ChatDigestState,
    ChatHistoryEntry,
    ChatRequest,
    ChatTurn,
    CompanionState,
    DayRecord,
    EvolutionLogEntry,
    FocusSession,
    Note,
    Personality,
    PersonalityParams,
    PersonalityUpdateRequest,
    RealtimeContext,
    Rhythm,
    RhythmPatterns,
    RoomScene,
    RoomState,
    Soul,
    SoulCreateRequest,
    StateEvent,
    UserMessage,
    WSMessage,
)
from .storage import FileStore, default_file_store

__version__ = "0.1.0"

__all__ = [
    # 顶层门面
    "CompanionAgent",
    "SoulAlreadyExists",
    "SoulNotInitialized",
    # 配置 & 事件
    "AgentConfig",
    "default_config",
    "EventBus",
    # 数据模型
    "BiasType",
    "ChatDigestState",
    "ChatHistoryEntry",
    "ChatRequest",
    "ChatTurn",
    "CompanionState",
    "DayRecord",
    "EvolutionLogEntry",
    "FocusSession",
    "Note",
    "Personality",
    "PersonalityParams",
    "PersonalityUpdateRequest",
    "RealtimeContext",
    "Rhythm",
    "RhythmPatterns",
    "RoomScene",
    "RoomState",
    "Soul",
    "SoulCreateRequest",
    "StateEvent",
    "UserMessage",
    "WSMessage",
    # 组件类
    "ContextManager",
    "Corpus",
    "FileStore",
    "LLMAdapter",
    "PersonalityEngine",
    "PersonalityPreset",
    "RelationshipDigester",
    "Scheduler",
    "StateMachine",
    # 模块级单例
    "default_context_manager",
    "default_corpus",
    "default_file_store",
    "default_llm_adapter",
    "default_personality_engine",
    "default_relationship_digester",
    "default_scheduler",
    "default_state_machine",
    # prompts / 辅助函数
    "PRESETS",
    "build_chat_system_prompt",
    "build_note_prompt",
    "build_personality_update_prompt",
    "build_relationship_digest_prompt",
    "build_say_one_line_prompt",
    "format_context_markdown_snapshot",
    "get_all_presets",
    "get_preset",
    "pick_line",
    "__version__",
]
