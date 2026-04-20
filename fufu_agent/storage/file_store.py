"""Local JSON file storage manager."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from ..config import AgentConfig, default_config

T = TypeVar("T", bound=BaseModel)


class FileStore:
    """基于本地 JSON / JSONL 的轻量持久层。

    ``data_dir`` 可以显式传入，否则使用传入 ``config`` 的 ``data_dir``。
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        *,
        config: Optional[AgentConfig] = None,
    ) -> None:
        cfg = config or default_config
        self.data_dir = Path(data_dir or cfg.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.data_dir / name

    def save(self, name: str, model: BaseModel) -> None:
        path = self._path(name)
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")

    def load(self, name: str, model_cls: Type[T]) -> Optional[T]:
        path = self._path(name)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        return model_cls.model_validate_json(raw)

    def save_raw(self, name: str, text: str) -> None:
        self._path(name).write_text(text, encoding="utf-8")

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path.exists():
            path.unlink()

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def append_jsonl(self, name: str, model: BaseModel) -> None:
        path = self._path(name)
        with open(path, "a", encoding="utf-8") as f:
            f.write(model.model_dump_json() + "\n")

    def read_jsonl(
        self, name: str, model_cls: Type[T], last_n: Optional[int] = None
    ) -> list[T]:
        path = self._path(name)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        lines = [l for l in lines if l.strip()]
        if last_n:
            lines = lines[-last_n:]
        return [model_cls.model_validate_json(line) for line in lines]

    def save_json_list(self, name: str, items: list[BaseModel]) -> None:
        path = self._path(name)
        data = [item.model_dump(mode="json") for item in items]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_json_list(self, name: str, model_cls: Type[T]) -> list[T]:
        path = self._path(name)
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [model_cls.model_validate(item) for item in raw]


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# 模块级默认实例（绑定 default_config.data_dir）
default_file_store = FileStore()


__all__ = ["FileStore", "DateTimeEncoder", "default_file_store"]
