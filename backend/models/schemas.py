"""
KampungKonekt Pydantic Data Schemas
Type-safe models for interactions, memory entries, flags, and reports.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class ConcernCategory(str, Enum):
    LONELINESS = "loneliness"
    FOOD_INSECURITY = "food_insecurity"
    PHYSICAL_PAIN = "physical_pain"
    MEDICATION_ISSUES = "medication_issues"
    DEPRESSION_SIGNS = "depression_signs"


class AlertSeverity(str, Enum):
    GREEN = "green"       # All clear
    YELLOW = "yellow"     # Mild concern — monitor
    RED = "red"           # Red flag — escalate


# ---------------------------------------------------------------------------
# Agnes API Request / Response
# ---------------------------------------------------------------------------

class AgnesIngestionRequest(BaseModel):
    """Payload sent to the Agnes Text API for contextual processing."""
    raw_text: str = Field(..., description="Raw transcribed text from the senior.")
    senior_id: str = Field(..., description="Unique identifier for the senior.")
    language_hint: Optional[str] = Field(
        "en", description="Best-guess language code (en, ms, zh, hak, tdd)."
    )
    context: Optional[str] = Field(
        None,
        description=(
            "Additional cultural context, e.g. 'Senior lives alone in HDB block 234, "
            "3rd floor, no neighbour visits this week.'"
        ),
    )


class AgnesIngestionResponse(BaseModel):
    """Response from the Agnes Text API."""
    translated_text: str = Field(..., description="Translated text in English.")
    sentiment: SentimentLabel = Field(..., description="Overall sentiment.")
    sentiment_score: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score 0-1."
    )
    concerns: list[ConcernCategory] = Field(
        default_factory=list, description="Identified welfare concern categories."
    )
    concern_details: list[dict] = Field(
        default_factory=list,
        description="Detailed per-concern extraction from Agnes.",
    )
    wellness_notes: str = Field(
        "", description="Agnes's plain-language wellness assessment."
    )
    suggested_response: str = Field(
        "", description="Friendly conversational reply for the senior."
    )
    detected_language: str = Field(
        "en", description="Language Agnes detected in the input."
    )


# ---------------------------------------------------------------------------
# Memory Entry (stored in SQLite)
# ---------------------------------------------------------------------------

class MemoryEntry(BaseModel):
    """A single logged interaction for a senior — time-series record."""
    id: Optional[int] = None
    senior_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    raw_text: str
    detected_language: str
    translated_text: str
    sentiment: SentimentLabel
    sentiment_score: float
    concerns: list[ConcernCategory] = Field(default_factory=list)
    concern_details: list[dict] = Field(default_factory=list)
    wellness_notes: str = ""
    suggested_response: str = ""

    # Serialization helpers for SQLite
    def to_row(self) -> tuple:
        return (
            self.id,
            self.senior_id,
            self.timestamp.isoformat(),
            self.raw_text,
            self.detected_language,
            self.translated_text,
            self.sentiment.value,
            self.sentiment_score,
            "|".join(c.value for c in self.concerns),
            str(self.concern_details),
            self.wellness_notes,
            self.suggested_response,
        )

    @staticmethod
    def from_row(row: tuple) -> "MemoryEntry":
        cols = [
            "id", "senior_id", "timestamp", "raw_text", "detected_language",
            "translated_text", "sentiment", "sentiment_score", "concerns",
            "concern_details", "wellness_notes", "suggested_response",
        ]
        d = dict(zip(cols, row))
        d["timestamp"] = datetime.fromisoformat(d["timestamp"])
        d["sentiment"] = SentimentLabel(d["sentiment"])
        d["concerns"] = [
            ConcernCategory(v) for v in d["concerns"].split("|") if v
        ] if isinstance(d["concerns"], str) else d["concerns"]
        d["concern_details"] = (
            eval(d["concern_details"]) if isinstance(d["concern_details"], str)
            else d["concern_details"]
        )
        return MemoryEntry(**d)


# ---------------------------------------------------------------------------
# Alert / Flag
# ---------------------------------------------------------------------------

class WelfareFlag(BaseModel):
    """A flag raised when anomaly detection thresholds are breached."""
    id: Optional[int] = None
    senior_id: str
    severity: AlertSeverity
    triggered_at: datetime = Field(default_factory=datetime.now)
    reason: str
    related_entry_ids: list[int] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class WelfareReport(BaseModel):
    """Structured welfare report for caseworkers / volunteers."""
    senior_id: str
    senior_name: str
    report_generated_at: datetime = Field(default_factory=datetime.now)
    period_start: datetime
    period_end: datetime
    total_interactions: int
    sentiment_summary: dict  # {positive: n, neutral: n, negative: n}
    concerns_timeline: list[dict]  # {date, category, detail}
    flags_triggered: list[WelfareFlag]
    risk_assessment: str
    recommended_actions: list[str]
    raw_markdown: str  # Full markdown-ready report string