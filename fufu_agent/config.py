"""FuFuAgent configuration.

两种使用方式：
1. 直接用模块级 ``default_config``：从进程环境变量和 ``.env`` 读取，适合脚本 / REPL。
2. ``AgentConfig(...)`` 显式实例化：适合在应用里按需隔离多个 Agent。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 包根：FuFuAgent/fufu_agent/config.py 的上两级就是 FuFuAgent 根目录
_PACKAGE_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_ROOT.parent

# 优先读取 FuFuAgent/.env，其次进程 env；已设置的进程环境变量拥有更高优先级
load_dotenv(_PROJECT_ROOT / ".env", override=False)


def _default_data_dir() -> Path:
    """优先使用环境变量 FUFU_DATA_DIR / COMPANION_DATA_DIR；否则落到包内默认 data/。"""
    env_dir = os.getenv("FUFU_DATA_DIR") or os.getenv("COMPANION_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return _PROJECT_ROOT / "data"


def _default_corpus_dir(data_dir: Path) -> Path:
    return data_dir / "corpus"


def _default_llm_providers() -> dict[str, dict[str, str]]:
    return {
        "siliconflow": {
            "base_url": os.getenv(
                "SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"
            ).rstrip("/"),
            "api_key": os.getenv("SILICONFLOW_API_KEY", ""),
            "model": os.getenv(
                "SILICONFLOW_MODEL", "Pro/MiniMaxAI/MiniMax-M2.5"
            ),
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
            "model": "deepseek-chat",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "model": "gpt-4o-mini",
        },
    }


class AgentConfig(BaseModel):
    """运行 FuFuAgent 所需的全部可调参数。

    所有字段都有默认值；外部 app 可按需覆盖。
    """

    app_name: str = "FuFuAgent"

    # 数据与语料目录
    data_dir: Path = Field(default_factory=_default_data_dir)
    corpus_dir: Optional[Path] = None

    # LLM
    llm_provider: str = Field(
        default_factory=lambda: os.getenv("FUFU_LLM_PROVIDER")
        or os.getenv("COMPANION_LLM_PROVIDER")
        or "siliconflow"
    )
    llm_providers: dict[str, dict[str, str]] = Field(
        default_factory=_default_llm_providers
    )

    # ---- 状态机相关 ----
    leaving_buffer_sec: float = 10.0
    night_start_hour: int = 22
    night_end_hour: int = 6
    auto_focus_minutes: int = 90

    # ---- 性格演化触发阈值 ----
    evo_event_threshold: int = 20
    evo_time_threshold_hours: float = 6.0

    # ---- 对话整理（关系 / 性格 / 灵魂 快照）阈值 ----
    digest_msg_threshold: int = 20
    digest_time_threshold_hours: float = 12.0

    # ---- 调度循环 ----
    scheduler_tick_sec: float = 60.0

    model_config = {"arbitrary_types_allowed": True}

    def model_post_init(self, __context: Any) -> None:  # pragma: no cover - trivial
        self.data_dir = Path(self.data_dir).expanduser().resolve()
        if self.corpus_dir is None:
            self.corpus_dir = _default_corpus_dir(self.data_dir)
        else:
            self.corpus_dir = Path(self.corpus_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.corpus_dir.mkdir(parents=True, exist_ok=True)

    # ---- Convenience ----

    @property
    def provider_entry(self) -> dict[str, str]:
        return self.llm_providers.get(self.llm_provider, {})

    @property
    def llm_configured(self) -> bool:
        cfg = self.provider_entry
        return bool(cfg.get("api_key") and cfg.get("base_url"))


# 模块级默认配置 —— 给"懒人模式"直接用。
default_config = AgentConfig()


__all__ = ["AgentConfig", "default_config"]
