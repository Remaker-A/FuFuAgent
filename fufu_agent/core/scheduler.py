"""Scheduler for periodic tasks: personality evolution triggers, digest triggers."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable, Optional, Union

from ..config import AgentConfig, default_config

logger = logging.getLogger(__name__)

AsyncCallback = Callable[[], Union[None, Awaitable[None]]]


async def _maybe_await(result: Union[None, Awaitable[None]]) -> None:
    if asyncio.iscoroutine(result) or asyncio.isfuture(result):
        await result


class Scheduler:
    """周期性后台任务。

    不直接依赖 ``PersonalityEngine`` / ``RelationshipDigester``，避免循环 import —— 
    由构造方（通常是 ``CompanionAgent``）注入两个 async 回调：``on_digest_due`` 与
    ``on_evolve_due``。
    """

    def __init__(
        self,
        *,
        config: Optional[AgentConfig] = None,
        on_digest_due: Optional[AsyncCallback] = None,
        on_evolve_due: Optional[AsyncCallback] = None,
    ) -> None:
        self.config = config or default_config
        self._on_digest_due = on_digest_due
        self._on_evolve_due = on_evolve_due

        self._event_count_since_update = 0
        self._last_evo_time: datetime = datetime.now()
        self._chat_msg_count_since_digest = 0
        self._last_digest_time: datetime = datetime.now()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ---- Callback registration (supports late binding) ----

    def set_digest_callback(self, cb: AsyncCallback) -> None:
        self._on_digest_due = cb

    def set_evolve_callback(self, cb: AsyncCallback) -> None:
        self._on_evolve_due = cb

    # ---- Event counters ----

    def record_event(self):
        self._event_count_since_update += 1

    def should_evolve(self) -> bool:
        if self._event_count_since_update >= self.config.evo_event_threshold:
            return True
        hours_since = (datetime.now() - self._last_evo_time).total_seconds() / 3600
        return hours_since >= self.config.evo_time_threshold_hours

    def mark_evolved(self):
        self._event_count_since_update = 0
        self._last_evo_time = datetime.now()

    def record_chat_message(self):
        self._chat_msg_count_since_digest += 1

    def should_digest(self) -> bool:
        if self._chat_msg_count_since_digest >= self.config.digest_msg_threshold:
            return True
        hours = (datetime.now() - self._last_digest_time).total_seconds() / 3600
        return (
            hours >= self.config.digest_time_threshold_hours
            and self._chat_msg_count_since_digest > 0
        )

    def mark_digested(self):
        self._chat_msg_count_since_digest = 0
        self._last_digest_time = datetime.now()

    # ---- Loop lifecycle ----

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _loop(self):
        tick = self.config.scheduler_tick_sec
        try:
            while self._running:
                await asyncio.sleep(tick)
                if self.should_digest() and self._on_digest_due:
                    try:
                        await _maybe_await(self._on_digest_due())
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.warning("Digest error: %s", e)
                if self.should_evolve() and self._on_evolve_due:
                    try:
                        await _maybe_await(self._on_evolve_due())
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.warning("Evolution error: %s", e)
        except asyncio.CancelledError:
            return


default_scheduler = Scheduler()


__all__ = ["Scheduler", "default_scheduler", "AsyncCallback"]
