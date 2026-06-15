"""
KampungKonekt Main Orchestrator
Ties together voice ingestion, Agnes API processing, memory storage,
anomaly detection, and report generation into a single workflow.

Usage:
    # Process a single voice interaction
    python main.py --process "Bo lang cai gia"

    # Run full welfare check for a senior
    python main.py --check senior_001

    # Generate a report manually
    python main.py --report senior_001

    # Simulate a week of interactions (demo mode)
    python main.py --simulate
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure backend/ is on the path
_BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(_BACKEND_DIR))

from api.agnes_client import AgnesClient
from models.schemas import (
    AgnesIngestionRequest,
    MemoryEntry,
    SentimentLabel,
    ConcernCategory,
)
from memory.storage import MemoryStorage
from analytics.detector import AnomalyDetector
from reports.generator import ReportGenerator
from config.settings import settings

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_BACKEND_DIR / "kampungkonekt.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("KampungKonekt")


# ---------------------------------------------------------------------------
# Core Workflow
# ---------------------------------------------------------------------------

class KampungKonektOrchestrator:
    """
    Main orchestrator that connects all backend components.

    Pipeline:
        Voice Input → Agnes Processing → Memory Storage →
        Anomaly Detection → Report Generation
    """

    def __init__(self) -> None:
        self._storage = MemoryStorage(db_path=settings.DB_PATH)
        self._agnes = AgnesClient()
        self._detector = AnomalyDetector(self._storage)
        self._reporter = ReportGenerator(self._storage)
        logger.info(
            "KampungKonekt initialized for senior: %s (%s)",
            settings.SENIOR_NAME,
            settings.SENIOR_ID,
        )

    # ------------------------------------------------------------------
    # Process a single voice interaction
    # ------------------------------------------------------------------

    def process_voice_input(
        self,
        raw_text: str,
        senior_id: Optional[str] = None,
        language_hint: str = "en",
    ) -> MemoryEntry:
        """
        Full pipeline: ingest voice text → process with Agnes → store → detect anomalies.

        Args:
            raw_text: Transcribed text from the senior's voice input.
            senior_id: Override default senior ID.
            language_hint: Best-guess language code.

        Returns:
            The stored MemoryEntry.
        """
        target_id = senior_id or settings.SENIOR_ID

        logger.info("Processing voice input for %s: '%s'", target_id, raw_text[:80])

        # Step 1: Send to Agnes for contextual processing
        request = AgnesIngestionRequest(
            raw_text=raw_text,
            senior_id=target_id,
            language_hint=language_hint,
            context=self._storage.get_recent_context(target_id, last_n=3),
        )
        agnes_response = self._agnes.ingest(request)

        logger.info(
            "Agnes processed: sentiment=%s concerns=%s lang=%s",
            agnes_response.sentiment.value,
            [c.value for c in agnes_response.concerns],
            agnes_response.detected_language,
        )

        # Step 2: Create and store memory entry
        entry = MemoryEntry(
            senior_id=target_id,
            raw_text=raw_text,
            detected_language=agnes_response.detected_language,
            translated_text=agnes_response.translated_text,
            sentiment=agnes_response.sentiment,
            sentiment_score=agnes_response.sentiment_score,
            concerns=agnes_response.concerns,
            concern_details=agnes_response.concern_details,
            wellness_notes=agnes_response.wellness_notes,
            suggested_response=agnes_response.suggested_response,
        )
        entry_id = self._storage.insert_entry(entry)
        entry.id = entry_id

        # Step 3: Run anomaly detection
        flags = self._detector.run_full_check(target_id)

        if flags:
            for flag in flags:
                self._storage.insert_flag(flag)
            logger.warning(
                "%d welfare flag(s) triggered for %s", len(flags), target_id
            )

        # Step 4: Check if report should be generated
        red_flags = [f for f in flags if f.severity.value == "red"]
        if red_flags:
            logger.info("Red flag detected — generating welfare report.")
            report = self._reporter.generate_welfare_report(
                senior_id=target_id, days=30, force_red_flag=True
            )
            if report:
                output_path = _BACKEND_DIR / "reports" / f"welfare_{target_id}_{datetime.now().strftime('%Y%m%d')}.md"
                self._reporter.save_report(report, str(output_path))
                logger.info("Welfare report saved to: %s", output_path)

        return entry

    # ------------------------------------------------------------------
    # Full welfare check
    # ------------------------------------------------------------------

    def run_welfare_check(
        self,
        senior_id: Optional[str] = None,
    ) -> dict:
        """
        Run a comprehensive welfare check: anomaly detection + report.

        Returns:
            Summary dict with risk level, flags, and report path.
        """
        target_id = senior_id or settings.SENIOR_ID

        logger.info("Running full welfare check for %s", target_id)

        # Run anomaly detection
        flags = self._detector.run_full_check(target_id)
        for flag in flags:
            self._storage.insert_flag(flag)

        # Get risk level
        risk_level, risk_desc = self._detector.get_risk_level(target_id)

        # Generate report if needed
        report = self._reporter.generate_welfare_report(
            senior_id=target_id, days=30, force_red_flag=bool(flags)
        )

        result = {
            "senior_id": target_id,
            "risk_level": risk_level.value,
            "risk_description": risk_desc,
            "flags_triggered": len(flags),
            "total_flags_all_time": len(self._storage.get_flags(target_id)),
            "recent_interactions": self._storage.get_total_interaction_count(target_id, days=30),
        }

        if report:
            output_path = _BACKEND_DIR / "reports" / f"welfare_{target_id}_{datetime.now().strftime('%Y%m%d')}.md"
            self._reporter.save_report(report, str(output_path))
            result["report_path"] = str(output_path)
            result["report_sentiment"] = report.sentiment_summary

        logger.info("Welfare check complete: %s", result)
        return result

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close database connection."""
        self._storage.close()
        logger.info("Orchestrator shut down cleanly.")

    def __enter__(self) -> "KampungKonektOrchestrator":
        return self

    def __exit__(self, *args) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Demo / Simulation Utilities
# ---------------------------------------------------------------------------

def simulate_week_of_interactions(orchestrator: KampungKonektOrchestrator) -> None:
    """
    Simulate a week of interactions for a senior who is gradually declining.
    Useful for testing the anomaly detection and reporting pipeline.
    """
    from datetime import timedelta

    senior_id = settings.SENIOR_ID

    # Simulated interactions over 7 days, trending negative
    simulations = [
        {
            "days_ago": 7,
            "raw_text": "Today I went to the market and bought some chicken rice. Very nice lah!",
            "language_hint": "en",
            "expected_sentiment": "positive",
        },
        {
            "days_ago": 6,
            "raw_text": "My daughter called me today. So happy! She said she will visit next week.",
            "language_hint": "en",
            "expected_sentiment": "positive",
        },
        {
            "days_ago": 5,
            "raw_text": "Had noodles for lunch alone. The neighbour went to market without me.",
            "language_hint": "en",
            "expected_sentiment": "neutral",
        },
        {
            "days_ago": 4,
            "raw_text": "Bo lang cai gia. Nobody cooks for me today. My stomach is hungry.",
            "language_hint": "en",
            "expected_sentiment": "negative",
        },
        {
            "days_ago": 3,
            "raw_text": "Send li sia. Nobody is here. I sit alone in the room all day.",
            "language_hint": "en",
            "expected_sentiment": "negative",
        },
        {
            "days_ago": 2,
            "raw_text": "My head hurts so much. Sakit kepala. Cannot sleep well also.",
            "language_hint": "en",
            "expected_sentiment": "negative",
        },
        {
            "days_ago": 1,
            "raw_text": "Bo u lang tsai. No one visits me. I feel so lonely. Want die already.",
            "language_hint": "en",
            "expected_sentiment": "negative",
        },
    ]

    logger.info("=" * 60)
    logger.info("SIMULATING ONE WEEK OF INTERACTIONS")
    logger.info("=" * 60)

    for sim in simulations:
        timestamp = datetime.now() - timedelta(days=sim["days_ago"])
        raw = sim["raw_text"]

        logger.info(
            "Day %d ago: '%s' [sentiment: %s]",
            sim["days_ago"],
            raw[:60],
            sim["expected_sentiment"],
        )

        entry = orchestrator.process_voice_input(
            raw_text=raw,
            senior_id=senior_id,
            language_hint=sim["language_hint"],
        )

        # Artificially set the timestamp (modify in DB)
        if entry.id:
            orchestrator._storage._conn.execute(
                "UPDATE memory_entries SET timestamp = ? WHERE id = ?",
                (timestamp.isoformat(), entry.id),
            )
            orchestrator._storage._conn.commit()

    logger.info("=" * 60)
    logger.info("SIMULATION COMPLETE — Running welfare check...")
    logger.info("=" * 60)

    # Run welfare check after simulation
    result = orchestrator.run_welfare_check(senior_id)
    logger.info("Welfare check result: %s", result)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KampungKonekt — Backend Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single voice interaction
  python main.py --process "Bo lang cai gia"

  # Run welfare check for a specific senior
  python main.py --check senior_001

  # Generate a report
  python main.py --report senior_001

  # Simulate a week of interactions (demo)
  python main.py --simulate
        """,
    )

    parser.add_argument(
        "--process",
        type=str,
        default=None,
        help="Process a single voice input (transcribed text).",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        help="Language hint: en, ms, zh, hak, tdd (default: en)",
    )
    parser.add_argument(
        "--check",
        type=str,
        default=None,
        help="Run full welfare check for a senior ID.",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Generate welfare report for a senior ID.",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Simulate a week of declining interactions for demo/testing.",
    )
    parser.add_argument(
        "--senior-id",
        type=str,
        default=None,
        help="Override default senior ID.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with KampungKonektOrchestrator() as orch:

        if args.simulate:
            # Run simulation
            simulate_week_of_interactions(orch)

        elif args.process:
            # Process single voice input
            entry = orch.process_voice_input(
                raw_text=args.process,
                senior_id=args.senior_id,
                language_hint=args.language,
            )
            print("\n" + "=" * 50)
            print("PROCESSING RESULT")
            print("=" * 50)
            print(f"  Raw Text:      {entry.raw_text}")
            print(f"  Translated:    {entry.translated_text}")
            print(f"  Language:      {entry.detected_language}")
            print(f"  Sentiment:     {entry.sentiment.value} ({entry.sentiment_score})")
            print(f"  Concerns:      {[c.value for c in entry.concerns] or 'None'}")
            print(f"  Wellness Note: {entry.wellness_notes}")
            print(f"  Suggested Reply: {entry.suggested_response}")
            print("=" * 50)

        elif args.check:
            # Run welfare check
            result = orch.run_welfare_check(args.check)
            print("\n" + "=" * 50)
            print("WELFARE CHECK RESULT")
            print("=" * 50)
            for key, value in result.items():
                print(f"  {key}: {value}")
            print("=" * 50)

        elif args.report:
            # Generate report only
            report = orch._reporter.generate_welfare_report(
                senior_id=args.report, days=30, force_red_flag=True
            )
            if report:
                output_path = _BACKEND_DIR / "reports" / f"welfare_{args.report}_{datetime.now().strftime('%Y%m%d')}.md"
                orch._reporter.save_report(report, str(output_path))
                print(f"\nReport saved to: {output_path}")
                print("\n--- Report Preview ---\n")
                print(report.raw_markdown[:1000])
                print("\n...")
            else:
                print("No report generated (no flags triggered).")

        else:
            # No arguments — show help
            print("""
KampungKonekt Backend Orchestrator
===================================

Usage examples:
  python main.py --process "Bo lang cai gia"
  python main.py --check senior_001
  python main.py --report senior_001
  python main.py --simulate

Run with --help for full options.
""")


if __name__ == "__main__":
    main()