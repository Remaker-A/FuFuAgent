"""Pydantic data models for all persistent and runtime data structures."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------- Enums ----------

class CompanionState(str, Enum):
    IDLE = "idle"
    PASSERBY = "passerby"
    COMPANION = "companion"
    FOCUS = "focus"
    DEEP_NIGHT = "deep_night"
    LEAVING = "leaving"


class BiasType(str, Enum):
    DECISIVE = "decisive"
    ADVENTUROUS = "adventurous"
    SLOW_DOWN = "slow_down"
    WARM_HUMOR = "warm_humor"
    NIGHT_OWL = "night_owl"
    BOOKISH = "bookish"
    CUSTOM = "custom"


# ---------- L0 Soul ----------

class Soul(BaseModel):
    created_at: datetime = Field(default_factory=datetime.now)
    current_state_word: str = ""
    struggle: str = ""
    user_facts: str = ""
    bias: BiasType = BiasType.DECISIVE
    opening_response: str = "你来了。"


# ---------- L1 Personality ----------

class PersonalityParams(BaseModel):
    bias: BiasType = BiasType.DECISIVE
    night_owl_index: float = 0.0
    anxiety_sensitivity: float = 0.0
    quietness: float = 0.5
    playfulness: float = 0.3
    attachment_level: float = 0.0


class EvolutionLogEntry(BaseModel):
    day: int = 0
    change: str = ""
    reason: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class Personality(BaseModel):
    version: int = 1
    updated_at: datetime = Field(default_factory=datetime.now)
    params: PersonalityParams = Field(default_factory=PersonalityParams)
    natural_description: str = "它刚刚来到这里，还在认识你。"
    voice_style: str = ""
    evolution_log: list[EvolutionLogEntry] = Field(default_factory=list)


# ---------- L2 Rhythm ----------

class DayRecord(BaseModel):
    date: str = ""
    first_arrive: str = ""
    last_leave: str = ""
    total_minutes: int = 0
    late_night: bool = False
    focus_sessions: int = 0
    state_switches: int = 0


class RhythmPatterns(BaseModel):
    avg_arrive: str = "09:00"
    avg_leave: str = "22:00"
    late_night_ratio: float = 0.0
    regularity_score: float = 0.5


class Rhythm(BaseModel):
    updated_at: str = ""
    days_together: int = 0
    recent_7_days: list[DayRecord] = Field(default_factory=list)
    patterns: RhythmPatterns = Field(default_factory=RhythmPatterns)


# ---------- L3 Realtime (in-memory) ----------

class RealtimeContext(BaseModel):
    current_state: CompanionState = CompanionState.IDLE
    state_since: datetime = Field(default_factory=datetime.now)
    seated_minutes: int = 0
    time_period: str = "morning"
    today_total_minutes: int = 0
    is_night: bool = False


# ---------- Events ----------

class StateEvent(BaseModel):
    type: str = "state_change"
    from_state: CompanionState = CompanionState.IDLE
    to_state: CompanionState = CompanionState.IDLE
    timestamp: datetime = Field(default_factory=datetime.now)


# ---------- Notes ----------

class Note(BaseModel):
    id: str = ""
    content: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    personality_version: int = 1


# ---------- Messages ----------

class UserMessage(BaseModel):
    content: str = ""
    mood: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


# ---------- Focus ----------

class FocusSession(BaseModel):
    active: bool = False
    started_at: Optional[datetime] = None
    duration_minutes: int = 25
    elapsed_minutes: int = 0


# ---------- API request/response ----------

class SoulCreateRequest(BaseModel):
    current_state_word: str
    struggle: str
    bias: BiasType
    custom_voice_style: Optional[str] = None


class PersonalityUpdateRequest(BaseModel):
    bias: Optional[BiasType] = None
    voice_style: Optional[str] = None


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatHistoryEntry(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatDigestState(BaseModel):
    """How many lines of chat_history.jsonl have been fed to relationship digest."""

    processed_lines: int = 0


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = Field(default_factory=list)


class WSMessage(BaseModel):
    type: str
    data: dict = Field(default_factory=dict)
