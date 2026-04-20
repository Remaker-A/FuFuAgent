"""Light-weight async event bus.

Agent 内部只负责把事件 publish 出去，至于要不要转发到 WebSocket / 桌面应用 / 日志，
由使用者自己注册订阅者决定。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Awaitable, Callable, Union

logger = logging.getLogger(__name__)

EventHandler = Callable[[str, dict[str, Any]], Union[None, Awaitable[None]]]


class EventBus:
    """支持同步或异步订阅者的最小 pub/sub 实现。"""

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> EventHandler:
        """注册一个订阅者；返回 handler 方便 ``unsubscribe`` 使用。"""
        self._handlers.append(handler)
        return handler

    def unsubscribe(self, handler: EventHandler) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

    def clear(self) -> None:
        self._handlers.clear()

    @property
    def subscriber_count(self) -> int:
        return len(self._handlers)

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """异步派发事件。任何订阅者抛出的异常都会被记录，但不影响其他订阅者。"""
        for handler in list(self._handlers):
            try:
                result = handler(event_type, data)
                if inspect.isawaitable(result):
                    await result
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "EventBus handler %s raised on '%s': %s", handler, event_type, exc
                )


__all__ = ["EventBus", "EventHandler"]
