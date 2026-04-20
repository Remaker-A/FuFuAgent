"""Offline corpus manager - fallback when LLM is unavailable."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from ..config import AgentConfig, default_config


class Corpus:
    """离线语料库。默认从 ``config.corpus_dir`` 里按状态名读取 JSON 文件。"""

    def __init__(
        self,
        corpus_dir: Optional[Path] = None,
        *,
        config: Optional[AgentConfig] = None,
    ) -> None:
        cfg = config or default_config
        self.corpus_dir = Path(corpus_dir or cfg.corpus_dir)
        self._cache: dict[str, list[dict]] = {}

    def _load(self, name: str) -> list[dict]:
        if name in self._cache:
            return self._cache[name]
        path = self.corpus_dir / f"{name}.json"
        if not path.exists():
            self._cache[name] = []
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        self._cache[name] = data
        return data

    def pick_line(self, state: str, time_period: str = "", **_: object) -> str:
        corpus = self._load(state)
        if not corpus:
            corpus = self._load("companion")
        if not corpus:
            return "嗯，你在。"

        candidates: list[dict] = []
        for entry in corpus:
            cond = entry.get("condition", {})
            if "time" in cond and cond["time"] != time_period:
                continue
            candidates.append(entry)

        if not candidates:
            candidates = corpus
        return random.choice(candidates).get("text", "嗯。")

    def reload(self) -> None:
        self._cache.clear()


default_corpus = Corpus()


def pick_line(state: str, time_period: str = "", **kwargs) -> str:
    """Backward-compatible module-level shim for ``default_corpus.pick_line``."""
    return default_corpus.pick_line(state, time_period, **kwargs)


__all__ = ["Corpus", "default_corpus", "pick_line"]
