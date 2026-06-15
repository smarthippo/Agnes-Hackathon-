"""
KampungKonekt Anomaly Detection Engine
Analyzes memory entries for welfare concerns and triggers alerts.

Detection Rules:
1. Consecutive Negative Days: 3+ days in a row with negative sentiment → Red Flag
2. Food Insecurity Spike: 2+ food-related concerns in 7 days → Yellow Flag
3. Loneliness Pattern: 3+ loneliness mentions in 7 days → Yellow Flag
4. Pain Emergency: Any mention of physical pain → Immediate Yellow Flag
5. Depression Keywords: Any depression-related phrases → Red Flag
6. Sudden Silence: No interaction for 3+ days (unusual for engaged seniors) → Monitor
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from memory.storage import MemoryStorage
from models.schemas import (
    AlertSeverity,
    ConcernCategory,
    MemoryEntry,
    WelfareFlag,
)
from config.settings import settings

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """
    Runs anomaly detection routines on senior memory data.

    Usage:
        detector = AnomalyDetector(storage)
        flags = detector.run_full_check(senior_id="senior_001")
    """

    def __init__(self, storage: MemoryStorage) -> None:
        self._storage = storage

    # ------------------------------------------------------------------
    # Main Entry Point
    # ------------------------------------------------------------------

    def run_full_check(self, senior_id: str) -> list[WelfareFlag]:
        """
        Run all detection rules and return any triggered flags.
        This is the main entry point for the anomaly detection pipeline.
        """
        flags: list[WelfareFlag] = []

        rules = [
            ("Consecutive Negative Sentiment", self._check_consecutive_negatives),
            ("Food Insecurity Pattern", self._check_food_insecurity),
            ("Loneliness Pattern", self._check_loneliness),
            ("Physical Pain Mention", self._check_physical_pain),
            ("Depression Indicators", self._check_depression),
            ("Interaction Silence", self._check_silence),
        ]

        for rule_name, rule_func in rules:
            try:
                rule_flags = rule_func(senior_id)
                flags.extend(rule_flags)
                if rule_flags:
                    logger.info("Rule '%s' triggered %d flag(s) for %s", rule_name, len(rule_flags), senior_id)
            except Exception as exc:
                logger.error("Rule '%s' failed for %s: %s", rule_name, senior_id, exc)

        return flags

    # ------------------------------------------------------------------
    # Detection Rule 1: Consecutive Negative Sentiment
    # ------------------------------------------------------------------

    def _check_consecutive_negatives(self, senior_id: str) -> list[WelfareFlag]:
        """
        Detect 3+ consecutive days with negative sentiment.
        Threshold configurable via settings.SENTIMENT_CONSECUTIVE_THRESHOLD.
        """
        threshold = settings.SENTIMENT_CONSECUTIVE_THRESHOLD
        consecutive_days = self._storage.get_consecutive_negative_days(
            senior_id, max_days=30
        )

        if consecutive_days < threshold:
            return []

        # Get the negative entries for context
        negative_entries = self._storage.get_entries_by_sentiment(
            senior_id, "negative", days=consecutive_days
        )
        related_ids = [e.id for e in negative_entries if e.id]

        # Check if a red flag already exists for this exact issue
        existing_flags = self._storage.get_flags(
            senior_id, severity=AlertSeverity.RED
        )
        for flag in existing_flags:
            if "consecutive negative" in flag.reason.lower():
                logger.info(
                    "Red flag already exists for consecutive negatives in %s, skipping",
                    senior_id,
                )
                return []

        severity = AlertSeverity.RED if consecutive_days >= 5 else AlertSeverity.YELLOW

        return [
            WelfareFlag(
                senior_id=senior_id,
                severity=severity,
                reason=(
                    f"{consecutive_days} consecutive day(s) with negative sentiment "
                    f"(threshold: {threshold})"
                ),
                related_entry_ids=related_ids[:20],  # Cap at 20 related IDs
                summary=(
                    f"⚠️ ALERT: Senior {senior_id} has shown negative sentiment for "
                    f"{consecutive_days} consecutive days. "
                    f"Immediate welfare check recommended."
                ),
            )
        ]

    # ------------------------------------------------------------------
    # Detection Rule 2: Food Insecurity Pattern
    # ------------------------------------------------------------------

    def _check_food_insecurity(self, senior_id: str) -> list[WelfareFlag]:
        """
        Detect 2+ food-related concerns within 7 days.
        """
        entries = self._storage.get_entries_by_concern(
            senior_id, ConcernCategory.FOOD_INSECURITY, days=7
        )

        if len(entries) < 2:
            return []

        related_ids = [e.id for e in entries if e.id]

        # Check for existing flag
        existing_flags = self._storage.get_flags(senior_id)
        for flag in existing_flags:
            if "food" in flag.reason.lower() and self._is_recent_flag(flag, hours=168):
                return []  # Already flagged

        return [
            WelfareFlag(
                senior_id=senior_id,
                severity=AlertSeverity.YELLOW,
                reason=f"Food insecurity mentioned {len(entries)} time(s) in the past 7 days",
                related_entry_ids=related_ids,
                summary=(
                    f"🍜 CONCERN: Senior {senior_id} has mentioned food insecurity "
                    f"{len(entries)} times in the past week. "
                    f"Consider arranging community meal delivery."
                ),
            )
        ]

    # ------------------------------------------------------------------
    # Detection Rule 3: Loneliness Pattern
    # ------------------------------------------------------------------

    def _check_loneliness(self, senior_id: str) -> list[WelfareFlag]:
        """
        Detect 3+ loneliness mentions within 7 days.
        """
        entries = self._storage.get_entries_by_concern(
            senior_id, ConcernCategory.LONELINESS, days=7
        )

        if len(entries) < 3:
            return []

        related_ids = [e.id for e in entries if e.id]

        # Check for existing flag
        existing_flags = self._storage.get_flags(senior_id)
        for flag in existing_flags:
            if "lonely" in flag.reason.lower() and self._is_recent_flag(flag, hours=168):
                return []

        return [
            WelfareFlag(
                senior_id=senior_id,
                severity=AlertSeverity.YELLOW,
                reason=f"Loneliness mentioned {len(entries)} time(s) in the past 7 days",
                related_entry_ids=related_ids,
                summary=(
                    f"👋 CONCERN: Senior {senior_id} has expressed loneliness "
                    f"{len(entries)} times in the past week. "
                    f"Volunteer visit or phone companion recommended."
                ),
            )
        ]

    # ------------------------------------------------------------------
    # Detection Rule 4: Physical Pain Mention (Immediate Alert)
    # ------------------------------------------------------------------

    def _check_physical_pain(self, senior_id: str) -> list[WelfareFlag]:
        """
        Any mention of physical pain triggers a Yellow Flag immediately.
        """
        entries = self._storage.get_entries_by_concern(
            senior_id, ConcernCategory.PHYSICAL_PAIN, days=3
        )

        if not entries:
            return []

        related_ids = [e.id for e in entries if e.id]

        # Check for existing recent flag
        existing_flags = self._storage.get_flags(senior_id)
        for flag in existing_flags:
            if "pain" in flag.reason.lower() and self._is_recent_flag(flag, hours=72):
                return []

        return [
            WelfareFlag(
                senior_id=senior_id,
                severity=AlertSeverity.YELLOW,
                reason=f"Physical pain mentioned {len(entries)} time(s) in the past 3 days",
                related_entry_ids=related_ids,
                summary=(
                    f"🏥 PAIN ALERT: Senior {senior_id} reported physical pain "
                    f"{len(entries)} time(s) recently. "
                    f"Medical check-up may be warranted."
                ),
            )
        ]

    # ------------------------------------------------------------------
    # Detection Rule 5: Depression Indicators
    # ------------------------------------------------------------------

    def _check_depression(self, senior_id: str) -> list[WelfareFlag]:
        """
        Any mention of depression signs triggers a Red Flag.
        """
        entries = self._storage.get_entries_by_concern(
            senior_id, ConcernCategory.DEPRESSION_SIGNS, days=14
        )

        if not entries:
            return []

        related_ids = [e.id for e in entries if e.id]

        # Check for existing red flag
        existing_flags = self._storage.get_flags(senior_id, severity=AlertSeverity.RED)
        for flag in existing_flags:
            if "depression" in flag.reason.lower() and self._is_recent_flag(flag, hours=336):
                return []

        return [
            WelfareFlag(
                senior_id=senior_id,
                severity=AlertSeverity.RED,
                reason=f"Depression indicators mentioned {len(entries)} time(s) in the past 14 days",
                related_entry_ids=related_ids,
                summary=(
                    f"🔴 CRITICAL: Senior {senior_id} has expressed depression indicators "
                    f"{len(entries)} time(s) in the past 2 weeks. "
                    f"Immediate professional intervention recommended."
                ),
            )
        ]

    # ------------------------------------------------------------------
    # Detection Rule 6: Interaction Silence
    # ------------------------------------------------------------------

    def _check_silence(self, senior_id: str) -> list[WelfareFlag]:
        """
        Detect unusual silence — no interactions for 3+ days when the senior
        has been actively engaging.
        """
        recent_entries = self._storage.get_entries(senior_id, days=14, limit=50)

        if len(recent_entries) < 3:
            return []  # Not enough data to establish baseline

        # Check if the last interaction was 3+ days ago
        latest = max(e.timestamp for e in recent_entries)
        days_since_last = (datetime.now() - latest).days

        if days_since_last < 3:
            return []

        # Check for existing silence flag
        existing_flags = self._storage.get_flags(senior_id)
        for flag in existing_flags:
            if "silence" in flag.reason.lower() and self._is_recent_flag(flag, hours=72):
                return []

        return [
            WelfareFlag(
                senior_id=senior_id,
                severity=AlertSeverity.GREEN,  # Monitor, not alarming
                reason=f"No interactions for {days_since_last} days (baseline: {len(recent_entries)} interactions in past 14 days)",
                related_entry_ids=[],
                summary=(
                    f"📵 MONITOR: Senior {senior_id} has been silent for {days_since_last} days. "
                    f"Previously averaged {len(recent_entries) / 14:.1f} interactions/day. "
                    f"Worth a wellness check call."
                ),
            )
        ]

    # ------------------------------------------------------------------
    # Utility Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_recent_flag(flag: WelfareFlag, hours: int = 24) -> bool:
        """Check if a flag was triggered within the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return flag.triggered_at >= cutoff

    def get_risk_level(self, senior_id: str) -> tuple[AlertSeverity, str]:
        """
        Calculate overall risk level for a senior based on all flags.

        Returns:
            Tuple of (severity, description)
        """
        red_flags = self._storage.get_flags(
            senior_id, severity=AlertSeverity.RED
        )
        yellow_flags = self._storage.get_flags(
            senior_id, severity=AlertSeverity.YELLOW
        )
        green_flags = self._storage.get_flags(
            senior_id, severity=AlertSeverity.GREEN
        )

        # Check for active (recent) red flags
        active_reds = [f for f in red_flags if self._is_recent_flag(f, hours=168)]

        if active_reds:
            return (
                AlertSeverity.RED,
                f"{len(active_reds)} active red flag(s) requiring immediate attention.",
            )

        if yellow_flags:
            active_yellows = [f for f in yellow_flags if self._is_recent_flag(f, hours=168)]
            if active_yellows:
                return (
                    AlertSeverity.YELLOW,
                    f"{len(active_yellows)} active yellow flag(s) — monitor closely.",
                )

        if green_flags:
            return (
                AlertSeverity.GREEN,
                "Monitoring level — no immediate concerns.",
            )

        return (
            AlertSeverity.GREEN,
            "All clear — no welfare flags detected.",
        )