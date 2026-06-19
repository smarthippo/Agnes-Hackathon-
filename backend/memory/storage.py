"""
KampungKonekt Memory Storage
SQLite-backed persistent storage for interaction memory entries and welfare flags.
Provides time-series query capabilities for trend analysis.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from models.schemas import MemoryEntry, WelfareFlag, AlertSeverity, ConcernCategory

logger = logging.getLogger(__name__)

# SQL schema for the memory database
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    senior_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    detected_language TEXT NOT NULL DEFAULT 'en',
    translated_text TEXT NOT NULL DEFAULT '',
    sentiment TEXT NOT NULL DEFAULT 'neutral',
    sentiment_score REAL NOT NULL DEFAULT 0.5,
    concerns TEXT NOT NULL DEFAULT '',
    concern_details TEXT NOT NULL DEFAULT '[]',
    wellness_notes TEXT NOT NULL DEFAULT '',
    suggested_response TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_memory_senior_timestamp
    ON memory_entries(senior_id, timestamp);

CREATE TABLE IF NOT EXISTS welfare_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    senior_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    triggered_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    related_entry_ids TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_flags_senior
    ON welfare_flags(senior_id, triggered_at);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    contact_name TEXT NOT NULL,
    contact_number TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    health_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


class MemoryStorage:
    """
    Persistent storage layer using SQLite.

    Usage:
        store = MemoryStorage()
        store.insert_entry(entry)
        entries = store.get_entries("senior_001", days=7)
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = Path(db_path) if db_path else None
        if not self._db_path:
            # Default: data/kampungkonekt.db relative to project root
            project_root = Path(__file__).parent.parent
            self._db_path = project_root / "data" / "kampungkonekt.db"

        # Ensure the data directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize the database
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(_CREATE_TABLES_SQL)
        self._conn.commit()
        # Migrate existing users table to add new columns if absent
        for col, default in [("language", "'en'"), ("health_notes", "''")]:
            try:
                self._conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
        logger.info("Memory storage initialized at %s", self._db_path)

    # ------------------------------------------------------------------
    # Memory Entry CRUD
    # ------------------------------------------------------------------

    def insert_entry(self, entry: MemoryEntry) -> int:
        """
        Insert a new memory entry. Returns the new row ID.
        """
        row = entry.to_row()
        cursor = self._conn.execute(
            """
            INSERT INTO memory_entries
                (id, senior_id, timestamp, raw_text, detected_language,
                 translated_text, sentiment, sentiment_score, concerns,
                 concern_details, wellness_notes, suggested_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        self._conn.commit()
        new_id = cursor.lastrowid
        entry.id = new_id
        logger.info("Inserted memory entry #%s for %s", new_id, entry.senior_id)
        return new_id

    def insert_entries(self, entries: list[MemoryEntry]) -> list[int]:
        """Batch insert multiple memory entries."""
        ids = []
        for entry in entries:
            row = entry.to_row()
            cursor = self._conn.execute(
                """
                INSERT INTO memory_entries
                    (id, senior_id, timestamp, raw_text, detected_language,
                     translated_text, sentiment, sentiment_score, concerns,
                     concern_details, wellness_notes, suggested_response)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            self._conn.commit()
            new_id = cursor.lastrowid
            entry.id = new_id
            ids.append(new_id)
        logger.info("Batch inserted %d entries for %s", len(ids), entries[0].senior_id if entries else "unknown")
        return ids

    def get_entry(self, entry_id: int) -> Optional[MemoryEntry]:
        """Retrieve a single memory entry by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM memory_entries WHERE id = ?", (entry_id,)
        )
        row = cursor.fetchone()
        if row:
            return MemoryEntry.from_row(row)
        return None

    def get_entries(
        self,
        senior_id: str,
        days: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[MemoryEntry]:
        """
        Retrieve memory entries for a senior.

        Args:
            senior_id: The senior's identifier.
            days: If set, only return entries from the last N days.
            limit: Maximum number of entries to return.
        """
        query = "SELECT * FROM memory_entries WHERE senior_id = ?"
        params: list = [senior_id]

        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            query += " AND timestamp >= ?"
            params.append(cutoff)

        query += " ORDER BY timestamp DESC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        cursor = self._conn.execute(query, params)
        return [MemoryEntry.from_row(row) for row in cursor.fetchall()]

    def get_entries_by_sentiment(
        self,
        senior_id: str,
        sentiment: str,
        days: Optional[int] = None,
    ) -> list[MemoryEntry]:
        """Retrieve entries filtered by sentiment label."""
        query = """
            SELECT * FROM memory_entries
            WHERE senior_id = ? AND sentiment = ?
        """
        params: list = [senior_id, sentiment]

        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            query += " AND timestamp >= ?"
            params.append(cutoff)

        query += " ORDER BY timestamp DESC"

        cursor = self._conn.execute(query, params)
        return [MemoryEntry.from_row(row) for row in cursor.fetchall()]

    def get_entries_by_concern(
        self,
        senior_id: str,
        concern: ConcernCategory,
        days: Optional[int] = None,
    ) -> list[MemoryEntry]:
        """Retrieve entries that mention a specific concern category."""
        query = """
            SELECT * FROM memory_entries
            WHERE senior_id = ? AND concerns LIKE ?
        """
        params: list = [senior_id, f"%{concern.value}%"]

        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            query += " AND timestamp >= ?"
            params.append(cutoff)

        query += " ORDER BY timestamp DESC"

        cursor = self._conn.execute(query, params)
        return [MemoryEntry.from_row(row) for row in cursor.fetchall()]

    def get_latest_entry(self, senior_id: str) -> Optional[MemoryEntry]:
        """Get the most recent memory entry for a senior."""
        return self.get_entries(senior_id, limit=1)

    def get_consecutive_negative_days(
        self,
        senior_id: str,
        max_days: int = 30,
    ) -> int:
        """
        Count consecutive days (from today backwards) with negative sentiment.
        Returns the count of consecutive negative days.
        """
        entries = self.get_entries(senior_id, days=max_days)

        # Group by date
        daily_sentiments: dict[str, str] = {}
        for entry in entries:
            date_str = entry.timestamp.strftime("%Y-%m-%d")
            # Keep the most dominant sentiment if multiple entries per day
            if entry.sentiment.value == "negative":
                daily_sentiments[date_str] = "negative"
            elif date_str not in daily_sentiments:
                daily_sentiments[date_str] = entry.sentiment.value

        # Count consecutive negative days from today
        consecutive = 0
        today = datetime.now().date()
        for i in range(max_days):
            day = today - timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            if daily_sentiments.get(day_str) == "negative":
                consecutive += 1
            else:
                # Only break if we've started finding negatives or if it's today
                if consecutive > 0 or day == today:
                    if consecutive > 0:
                        break
                    # If today is not negative, check if there are any
                    # negative days in history
                    if day_str not in daily_sentiments or daily_sentiments[day_str] != "negative":
                        if consecutive == 0 and day == today:
                            continue
                        break

        return consecutive

    def get_negative_days_with_gaps(
        self,
        senior_id: str,
        days: int = 30,
    ) -> list[dict]:
        """
        More robust: count consecutive negative days allowing for gaps
        (missing days without entries are not counted as negative).
        Returns a list of dicts with date, sentiment, entry_count.
        """
        entries = self.get_entries(senior_id, days=days)

        # Group by date
        daily_data: dict[str, list] = {}
        for entry in entries:
            date_str = entry.timestamp.strftime("%Y-%m-%d")
            if date_str not in daily_data:
                daily_data[date_str] = []
            daily_data[date_str].append(entry.sentiment.value)

        # Determine dominant sentiment per day
        daily_sentiments: dict[str, str] = {}
        for date_str, sentiments in daily_data.items():
            from collections import Counter
            counter = Counter(sentiments)
            daily_sentiments[date_str] = counter.most_common(1)[0][0]

        # Count consecutive negative days from today (skipping days with no data)
        consecutive = 0
        today = datetime.now().date()
        gap_allowed = True  # Allow gaps at the very end

        for i in range(days):
            day = today - timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")

            if day_str in daily_sentiments:
                if daily_sentiments[day_str] == "negative":
                    consecutive += 1
                else:
                    break

        return consecutive

    # ------------------------------------------------------------------
    # Welfare Flags
    # ------------------------------------------------------------------

    def insert_flag(self, flag: WelfareFlag) -> int:
        """Insert a new welfare flag."""
        row = (
            flag.id,
            flag.senior_id,
            flag.severity.value,
            flag.triggered_at.isoformat(),
            flag.reason,
            str(flag.related_entry_ids),
            flag.summary,
        )
        cursor = self._conn.execute(
            """
            INSERT INTO welfare_flags
                (id, senior_id, severity, triggered_at, reason,
                 related_entry_ids, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        self._conn.commit()
        new_id = cursor.lastrowid
        flag.id = new_id
        logger.info(
            "Inserted welfare flag #%s [%s] for %s",
            new_id, flag.severity.value, flag.senior_id,
        )
        return new_id

    def get_flags(
        self,
        senior_id: str,
        severity: Optional[AlertSeverity] = None,
    ) -> list[WelfareFlag]:
        """Retrieve welfare flags for a senior."""
        query = "SELECT * FROM welfare_flags WHERE senior_id = ?"
        params: list = [senior_id]

        if severity:
            query += " AND severity = ?"
            params.append(severity.value)

        query += " ORDER BY triggered_at DESC"

        cursor = self._conn.execute(query, params)
        flags = []
        for row in cursor.fetchall():
            flag = WelfareFlag(
                id=row[0],
                senior_id=row[1],
                severity=AlertSeverity(row[2]),
                triggered_at=datetime.fromisoformat(row[3]),
                reason=row[4],
                related_entry_ids=eval(row[5]) if isinstance(row[5], str) else row[5],
                summary=row[6],
            )
            flags.append(flag)
        return flags

    def has_active_red_flag(self, senior_id: str, hours: int = 24) -> bool:
        """Check if there's an active red flag within the specified hours."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        cursor = self._conn.execute(
            """
            SELECT COUNT(*) FROM welfare_flags
            WHERE senior_id = ? AND severity = 'red' AND triggered_at >= ?
            """,
            (senior_id, cutoff),
        )
        count = cursor.fetchone()[0]
        return count > 0

    # ------------------------------------------------------------------
    # Summary / Analytics Queries
    # ------------------------------------------------------------------

    def get_sentiment_summary(
        self,
        senior_id: str,
        days: int = 30,
    ) -> dict[str, int]:
        """
        Get a count of each sentiment type over the last N days.
        Returns e.g. {"positive": 5, "neutral": 8, "negative": 3}
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = self._conn.execute(
            """
            SELECT sentiment, COUNT(*) as cnt
            FROM memory_entries
            WHERE senior_id = ? AND timestamp >= ?
            GROUP BY sentiment
            """,
            (senior_id, cutoff),
        )
        result: dict[str, int] = {"positive": 0, "neutral": 0, "negative": 0}
        for row in cursor.fetchall():
            result[row[0]] = row[1]
        return result

    def get_concern_summary(
        self,
        senior_id: str,
        days: int = 30,
    ) -> dict[str, int]:
        """
        Get a count of each concern category over the last N days.
        Returns e.g. {"loneliness": 5, "food_insecurity": 3, ...}
        """
        entries = self.get_entries(senior_id, days=days)
        counts: dict[str, int] = {}
        for entry in entries:
            for concern in entry.concerns:
                key = concern.value
                counts[key] = counts.get(key, 0) + 1
        return counts

    def get_total_interaction_count(
        self,
        senior_id: str,
        days: Optional[int] = None,
    ) -> int:
        """Get total number of interactions for a senior."""
        query = "SELECT COUNT(*) FROM memory_entries WHERE senior_id = ?"
        params: list = [senior_id]

        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            query += " AND timestamp >= ?"
            params.append(cutoff)

        cursor = self._conn.execute(query, params)
        return cursor.fetchone()[0]

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def get_recent_context(
        self,
        senior_id: str,
        last_n: int = 5,
    ) -> str:
        """
        Get a text summary of the last N interactions for context
        injection into Agnes API calls.
        """
        entries = self.get_entries(senior_id, limit=last_n)
        if not entries:
            return "No previous interactions on record."

        parts: list[str] = []
        for entry in reversed(entries):  # Oldest first
            parts.append(
                f"- {entry.timestamp.strftime('%Y-%m-%d %H:%M')}: "
                f"'{entry.raw_text}' "
                f"(sentiment: {entry.sentiment.value}, "
                f"concerns: {', '.join(c.value for c in entry.concerns) or 'none'})"
            )

        return "Recent conversation history:\n" + "\n".join(parts)

    # ------------------------------------------------------------------
    # User CRUD
    # ------------------------------------------------------------------

    def create_user(self, name: str, contact_name: str, contact_number: str,
                    language: str = "en", health_notes: str = "") -> dict:
        """Create a new user. Raises ValueError if name already exists."""
        try:
            self._conn.execute(
                "INSERT INTO users (name, contact_name, contact_number, language, health_notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, contact_name, contact_number, language, health_notes, datetime.now().isoformat()),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"User '{name}' already exists.")
        return self.get_user(name)

    def get_all_users(self) -> list[dict]:
        """Fetch all users ordered by creation date."""
        rows = self._conn.execute(
            "SELECT id, name, contact_name, contact_number, language, health_notes, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
        return [{"id": r[0], "name": r[1], "contact_name": r[2], "contact_number": r[3],
                 "language": r[4], "health_notes": r[5], "created_at": r[6]} for r in rows]

    def get_user(self, name: str) -> Optional[dict]:
        """Fetch a user by name. Returns None if not found."""
        row = self._conn.execute(
            "SELECT id, name, contact_name, contact_number, language, health_notes, created_at FROM users WHERE name = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "contact_name": row[2], "contact_number": row[3],
                "language": row[4], "health_notes": row[5], "created_at": row[6]}

    def update_user(self, current_name: str, name: str, contact_name: str, contact_number: str,
                    language: str = "en", health_notes: str = "") -> Optional[dict]:
        """Update a user's profile. Returns updated user or None if not found."""
        existing = self.get_user(current_name)
        if not existing:
            return None
        try:
            self._conn.execute(
                "UPDATE users SET name = ?, contact_name = ?, contact_number = ?, language = ?, health_notes = ? WHERE name = ? COLLATE NOCASE",
                (name, contact_name, contact_number, language, health_notes, current_name),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"User '{name}' already exists.")
        return self.get_user(name)

    def save_user_language(self, name: str, language: str) -> None:
        """Update just the language preference for a user."""
        self._conn.execute(
            "UPDATE users SET language = ? WHERE name = ? COLLATE NOCASE",
            (language, name),
        )
        self._conn.commit()

    def get_user_history_for_ai(self, senior_id: str, last_n: int = 5) -> list[dict]:
        """Return the last N interactions formatted for passing to Gemini."""
        entries = self.get_entries(senior_id, limit=last_n)
        result = []
        for entry in reversed(entries):
            result.append({
                "date": entry.timestamp.strftime("%Y-%m-%d"),
                "said": entry.raw_text,
                "sentiment": entry.sentiment.value,
                "concerns": [c.value for c in entry.concerns],
            })
        return result

    def delete_user(self, name: str) -> bool:
        """Delete a user by name. Returns True if deleted, False if not found."""
        cursor = self._conn.execute("DELETE FROM users WHERE name = ? COLLATE NOCASE", (name,))
        self._conn.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.info("Memory storage connection closed.")

    def __enter__(self) -> "MemoryStorage":
        return self

    def __exit__(self, *args) -> None:
        self.close()