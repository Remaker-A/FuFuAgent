"""LLM 适配层 + Prompt 模板 + 离线语料兜底 + 性格预设。"""

from .adapter import LLMAdapter, default_llm_adapter
from .corpus import Corpus, default_corpus
from .presets import (
    PRESETS,
    PersonalityPreset,
    get_all_presets,
    get_preset,
)
from .prompts import (
    build_chat_system_prompt,
    build_note_prompt,
    build_personality_update_prompt,
    build_relationship_digest_prompt,
    build_say_one_line_prompt,
    format_context_markdown_snapshot,
)

__all__ = [
    "LLMAdapter",
    "default_llm_adapter",
    "Corpus",
    "default_corpus",
    "PRESETS",
    "PersonalityPreset",
    "get_all_presets",
    "get_preset",
    "build_chat_system_prompt",
    "build_note_prompt",
    "build_personality_update_prompt",
    "build_relationship_digest_prompt",
    "build_say_one_line_prompt",
    "format_context_markdown_snapshot",
]
