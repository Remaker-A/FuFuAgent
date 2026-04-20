"""State machine engine with 6 states for the companion agent."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Awaitable, Callable, Optional, Union

from ..config import AgentConfig, default_config
from ..models import (
    CompanionState,
    FocusSession,
    RealtimeContext,
    StateEvent,
)

StateChangeListener = Callable[[StateEvent], Union[None, Awaitable[None]]]


class StateMachine:
    def __init__(self, *, config: Optional[AgentConfig] = None) -> None:
        self.config = config or default_config
        self.ctx = RealtimeContext()
        self.focus = FocusSession()
        self._listeners: list[StateChangeListener] = []
        self._simulated_time: Optional[datetime] = None
        self._leaving_task: Optional[asyncio.Task] = None

    @property
    def now(self) -> datetime:
        return self._simulated_time or datetime.now()

    def set_simulated_time(self, hour: int, minute: int = 0):
        n = datetime.now()
        self._simulated_time = n.replace(hour=hour, minute=minute, second=0)

    def clear_simulated_time(self):
        self._simulated_time = None

    def on_state_change(self, callback: StateChangeListener) -> StateChangeListener:
        self._listeners.append(callback)
        return callback

    def is_night(self) -> bool:
        h = self.now.hour
        return (
            h >= self.config.night_start_hour or h < self.config.night_end_hour
        )

    # keep backward compat alias
    _is_night = is_night

    def time_period(self) -> str:
        h = self.now.hour
        if 5 <= h < 12:
            return "morning"
        if 12 <= h < 14:
            return "noon"
        if 14 <= h < 18:
            return "afternoon"
        if 18 <= h < 22:
            return "evening"
        return "late_night"

    _time_period = time_period

    def _update_ctx(self):
        self.ctx.is_night = self._is_night()
        self.ctx.time_period = self._time_period()
        elapsed = (self.now - self.ctx.state_since).total_seconds()
        if self.ctx.current_state in (
            CompanionState.COMPANION,
            CompanionState.FOCUS,
            CompanionState.DEEP_NIGHT,
        ):
            self.ctx.seated_minutes = int(elapsed / 60)

    async def _notify(self, old: CompanionState, new: CompanionState):
        event = StateEvent(
            from_state=old,
            to_state=new,
            distance_cm=self.ctx.distance_cm,
            timestamp=self.now,
        )
        for cb in self._listeners:
            result = cb(event)
            if asyncio.iscoroutine(result):
                await result

    async def transition_to(self, new_state: CompanionState) -> bool:
        old = self.ctx.current_state
        if old == new_state:
            return False

        if not self._is_valid_transition(old, new_state):
            return False

        if self._leaving_task and not self._leaving_task.done():
            self._leaving_task.cancel()
            self._leaving_task = None

        self.ctx.current_state = new_state
        self.ctx.state_since = self.now
        self._update_ctx()

        await self._notify(old, new_state)
        return True

    def _is_valid_transition(self, old: CompanionState, new: CompanionState) -> bool:
        valid = {
            CompanionState.IDLE: {CompanionState.PASSERBY},
            CompanionState.PASSERBY: {CompanionState.IDLE, CompanionState.COMPANION},
            CompanionState.COMPANION: {
                CompanionState.FOCUS,
                CompanionState.DEEP_NIGHT,
                CompanionState.LEAVING,
            },
            CompanionState.FOCUS: {
                CompanionState.COMPANION,
                CompanionState.DEEP_NIGHT,
                CompanionState.LEAVING,
            },
            CompanionState.DEEP_NIGHT: {CompanionState.LEAVING},
            CompanionState.LEAVING: {CompanionState.IDLE},
        }
        return new in valid.get(old, set())

    async def person_arrive(self, distance_cm: float = 150.0):
        self.ctx.distance_cm = distance_cm
        if self.ctx.current_state == CompanionState.IDLE:
            await self.transition_to(CompanionState.PASSERBY)

    async def person_sit(self, distance_cm: float = 50.0):
        self.ctx.distance_cm = distance_cm
        cur = self.ctx.current_state
        target = CompanionState.COMPANION
        if self._is_night():
            target = CompanionState.DEEP_NIGHT

        if cur == CompanionState.PASSERBY:
            await self.transition_to(target)
        elif cur == CompanionState.IDLE:
            await self.transition_to(CompanionState.PASSERBY)
            await self.transition_to(target)

    async def person_leave(self):
        self.ctx.distance_cm = 999.0
        cur = self.ctx.current_state
        if cur in (
            CompanionState.COMPANION,
            CompanionState.FOCUS,
            CompanionState.DEEP_NIGHT,
        ):
            await self.transition_to(CompanionState.LEAVING)
            self._leaving_task = asyncio.create_task(self._leaving_to_idle())
        elif cur == CompanionState.PASSERBY:
            await self.transition_to(CompanionState.IDLE)

    async def _leaving_to_idle(self):
        await asyncio.sleep(self.config.leaving_buffer_sec)
        if self.ctx.current_state == CompanionState.LEAVING:
            await self.transition_to(CompanionState.IDLE)

    async def start_focus(self, duration_minutes: int = 25):
        if self.ctx.current_state == CompanionState.COMPANION:
            self.focus = FocusSession(
                active=True,
                started_at=self.now,
                duration_minutes=duration_minutes,
            )
            await self.transition_to(CompanionState.FOCUS)

    async def stop_focus(self):
        if self.ctx.current_state == CompanionState.FOCUS:
            self.focus.active = False
            target = (
                CompanionState.DEEP_NIGHT
                if self._is_night()
                else CompanionState.COMPANION
            )
            await self.transition_to(target)

    def get_status(self) -> dict:
        self._update_ctx()
        return {
            "state": self.ctx.current_state.value,
            "state_since": self.ctx.state_since.isoformat(),
            "seated_minutes": self.ctx.seated_minutes,
            "distance_cm": self.ctx.distance_cm,
            "time_period": self.ctx.time_period,
            "is_night": self.ctx.is_night,
            "today_total_minutes": self.ctx.today_total_minutes,
            "focus": {
                "active": self.focus.active,
                "duration_minutes": self.focus.duration_minutes,
                "started_at": (
                    self.focus.started_at.isoformat() if self.focus.started_at else None
                ),
            },
        }


default_state_machine = StateMachine()


__all__ = ["StateMachine", "StateChangeListener", "default_state_machine"]
