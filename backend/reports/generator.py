"""
KampungKonekt Welfare Report Generator
Compiles structured markdown reports for Family Service Centres (FSC),
community caseworkers, and SMU Student Volunteer groups.

Reports are generated when Red Flags are triggered or on-demand for
scheduled welfare reviews.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from memory.storage import MemoryStorage
from analytics.detector import AnomalyDetector
from models.schemas import WelfareFlag, WelfareReport, ConcernCategory, AlertSeverity
from config.settings import settings

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates welfare reports in markdown format.

    Usage:
        generator = ReportGenerator(storage)
        report = generator.generate_welfare_report(senior_id="senior_001")
        # Save to file
        generator.save_report(report, "reports/welfare_2026-06-15.md")
    """

    def __init__(self, storage: MemoryStorage) -> None:
        self._storage = storage
        self._detector = AnomalyDetector(storage)

    # ------------------------------------------------------------------
    # Main Entry Point
    # ------------------------------------------------------------------

    def generate_welfare_report(
        self,
        senior_id: Optional[str] = None,
        days: int = 30,
        force_red_flag: bool = False,
    ) -> Optional[WelfareReport]:
        """
        Generate a comprehensive welfare report.

        Args:
            senior_id: Target senior (defaults to settings.SENIOR_ID).
            days: Number of days to look back.
            force_red_flag: If True, generate report even without red flags.
        """
        target_id = senior_id or settings.SENIOR_ID

        # Check if we should generate (red flag exists or forced)
        if not force_red_flag:
            has_red = self._storage.has_active_red_flag(target_id, hours=days * 24)
            if not has_red:
                # Also check for multiple yellow flags
                yellow_flags = self._storage.get_flags(
                    target_id, severity=AlertSeverity.YELLOW
                )
                active_yellows = [
                    f for f in yellow_flags
                    if self._detector._is_recent_flag(f, hours=days * 12)
                ]
                if len(active_yellows) < 2:
                    logger.info(
                        "No red flag or sufficient yellow flags for %s, skipping report.",
                        target_id,
                    )
                    return None

        # Gather data
        period_end = datetime.now()
        period_start = period_end - timedelta(days=days)

        entries = self._storage.get_entries(target_id, days=days)
        sentiment_summary = self._storage.get_sentiment_summary(target_id, days)
        concern_summary = self._storage.get_concern_summary(target_id, days)
        flags = self._storage.get_flags(target_id)
        risk_level, risk_desc = self._detector.get_risk_level(target_id)

        # Build concerns timeline
        concerns_timeline = self._build_concerns_timeline(entries)

        # Build recommended actions
        actions = self._generate_recommended_actions(risk_level, flags, concern_summary)

        # Build risk assessment
        risk_assessment = self._build_risk_assessment(risk_level, risk_desc, flags, entries)

        # Build markdown
        markdown = self._render_markdown(
            senior_id=target_id,
            senior_name=settings.SENIOR_NAME,
            period_start=period_start,
            period_end=period_end,
            total_interactions=len(entries),
            sentiment_summary=sentiment_summary,
            concerns_timeline=concerns_timeline,
            flags_triggered=flags,
            risk_assessment=risk_assessment,
            recommended_actions=actions,
            risk_level=risk_level,
        )

        report = WelfareReport(
            senior_id=target_id,
            senior_name=settings.SENIOR_NAME,
            period_start=period_start,
            period_end=period_end,
            total_interactions=len(entries),
            sentiment_summary=sentiment_summary,
            concerns_timeline=concerns_timeline,
            flags_triggered=flags,
            risk_assessment=risk_assessment,
            recommended_actions=actions,
            raw_markdown=markdown,
        )

        logger.info(
            "Generated welfare report for %s: %d interactions, risk=%s",
            target_id, len(entries), risk_level.value,
        )

        return report

    # ------------------------------------------------------------------
    # Report Rendering
    # ------------------------------------------------------------------

    def _render_markdown(
        self,
        senior_id: str,
        senior_name: str,
        period_start: datetime,
        period_end: datetime,
        total_interactions: int,
        sentiment_summary: dict,
        concerns_timeline: list[dict],
        flags_triggered: list[WelfareFlag],
        risk_assessment: str,
        recommended_actions: list[str],
        risk_level,
    ) -> str:
        """Render the full markdown report string."""

        # Header
        lines: list[str] = []
        lines.append("# Welfare Report — KampungKonekt")
        lines.append("")
        lines.append(f"**Report Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')} SGT")
        lines.append(f"**Report Period:** {period_start.strftime('%Y-%m-%d')} to {period_end.strftime('%Y-%m-%d')}")
        lines.append(f"**Senior ID:** `{senior_id}`")
        lines.append(f"**Senior Name:** {senior_name}")
        lines.append("")

        # Risk Level Banner
        risk_banner = {
            "red": "🔴 **HIGH RISK — Immediate attention required**",
            "yellow": "🟡 **MEDIUM RISK — Close monitoring recommended**",
            "green": "🟢 **LOW RISK — No immediate concerns**",
        }
        banner = risk_banner.get(risk_level.value, "⚪ **Unknown risk level**")
        lines.append(f"> {banner}")
        lines.append("")

        # Summary Statistics
        lines.append("## 📊 Summary Statistics")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Interactions | {total_interactions} |")
        lines.append(
            f"| Positive Sentiment | {sentiment_summary.get('positive', 0)} |"
        )
        lines.append(
            f"| Neutral Sentiment | {sentiment_summary.get('neutral', 0)} |"
        )
        lines.append(
            f"| Negative Sentiment | {sentiment_summary.get('negative', 0)} |"
        )
        lines.append("")

        # Sentiment Breakdown
        lines.append("### Sentiment Breakdown")
        lines.append("")
        pos = sentiment_summary.get("positive", 0)
        neu = sentiment_summary.get("neutral", 0)
        neg = sentiment_summary.get("negative", 0)
        total = pos + neu + neg
        if total > 0:
            lines.append(
                f"- **😊 Positive:** {pos}/{total} ({pos/total*100:.0f}%)"
            )
            lines.append(
                f"- **😐 Neutral:** {neu}/{total} ({neu/total*100:.0f}%)"
            )
            lines.append(
                f"- **😟 Negative:** {neg}/{total} ({neg/total*100:.0f}%)"
            )
        else:
            lines.append("- No sentiment data available.")
        lines.append("")

        # Welfare Flags
        if flags_triggered:
            lines.append("## 🚩 Welfare Flags")
            lines.append("")
            for flag in flags_triggered:
                icon = {"red": "🔴", "yellow": "🟡", "green": "🟢"}.get(
                    flag.severity.value, "⚪"
                )
                lines.append(
                    f"- {icon} **[{flag.severity.value.upper()}]** "
                    f"{flag.reason}"
                )
                lines.append(f"  - Triggered: {flag.triggered_at.strftime('%Y-%m-%d %H:%M')}")
                if flag.summary:
                    lines.append(f"  - {flag.summary}")
            lines.append("")

        # Concerns Timeline
        if concerns_timeline:
            lines.append("## 📅 Concerns Timeline")
            lines.append("")
            lines.append("| Date | Category | Detail |")
            lines.append("|------|----------|--------|")
            for item in sorted(concerns_timeline, key=lambda x: x["date"]):
                lines.append(
                    f"| {item['date']} | {item['category']} | {item['detail']} |"
                )
            lines.append("")

        # Risk Assessment
        lines.append("## 🔍 Risk Assessment")
        lines.append("")
        lines.append(risk_assessment)
        lines.append("")

        # Recommended Actions
        if recommended_actions:
            lines.append("## ✅ Recommended Actions")
            lines.append("")
            for i, action in enumerate(recommended_actions, 1):
                lines.append(f"{i}. {action}")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append(
            "*This report was automatically generated by KampungKonekt's Agentic Memory system.*"
        )
        lines.append(
            "*For emergencies, dial **995** or contact the senior's emergency contact.*"
        )
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Data Builders
    # ------------------------------------------------------------------

    def _build_concerns_timeline(
        self, entries: list
    ) -> list[dict]:
        """Build a timeline of welfare concerns from memory entries."""
        timeline: list[dict] = []

        for entry in sorted(entries, key=lambda e: e.timestamp):
            for concern in entry.concerns:
                timeline.append({
                    "date": entry.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "category": concern.value,
                    "detail": entry.raw_text[:100],  # Truncate long texts
                    "sentiment": entry.sentiment.value,
                    "entry_id": entry.id,
                })

        return timeline

    def _generate_recommended_actions(
        self,
        risk_level,
        flags: list[WelfareFlag],
        concern_summary: dict,
    ) -> list[str]:
        """Generate action items based on risk assessment."""
        actions: list[str] = []

        if risk_level.value == "red":
            actions.append(
                "🔴 **URGENT:** Schedule immediate welfare check visit within 24 hours."
            )
            actions.append(
                "📞 Contact the assigned caseworker at the Family Service Centre."
            )

        if concern_summary.get("food_insecurity", 0) > 0:
            actions.append(
                "🍜 Arrange community meal delivery (e.g., Meals on Wheels or hawker centre visit)."
            )

        if concern_summary.get("loneliness", 0) > 0:
            actions.append(
                "👋 Assign an SMU Student Volunteer for regular companionship calls or visits."
            )

        if concern_summary.get("physical_pain", 0) > 0:
            actions.append(
                "🏥 Recommend a medical check-up or home visit by a community nurse."
            )

        if concern_summary.get("depression_signs", 0) > 0:
            actions.append(
                "🧠 Refer to SG Enable or IMH's community mental health programme."
            )

        if concern_summary.get("medication_issues", 0) > 0:
            actions.append(
                "💊 Arrange medicine delivery or set up a pill dispenser with alarms."
            )

        if not actions:
            actions.append(
                "📋 Continue routine monitoring. No immediate intervention required."
            )

        return actions

    def _build_risk_assessment(
        self,
        risk_level,
        risk_desc: str,
        flags: list[WelfareFlag],
        entries: list,
    ) -> str:
        """Build the narrative risk assessment section."""
        lines: list[str] = []

        lines.append(risk_desc)
        lines.append("")

        # Contextual details
        negative_count = sum(1 for e in entries if e.sentiment.value == "negative")
        if negative_count > 0:
            lines.append(
                f"- **{negative_count}** out of **{len(entries)}** interactions "
                f"showed negative sentiment."
            )

        red_flags = [f for f in flags if f.severity.value == "red"]
        if red_flags:
            lines.append(
                f"- **{len(red_flags)} red flag(s)** have been triggered in this period."
            )
            for flag in red_flags:
                lines.append(f"  - '{flag.reason}'")

        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # File Operations
    # ------------------------------------------------------------------

    def save_report(
        self,
        report: WelfareReport,
        output_path: str,
    ) -> str:
        """Save the report markdown to a file."""
        from pathlib import Path

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.raw_markdown, encoding="utf-8")

        logger.info("Welfare report saved to %s", path)
        return str(path)

    def send_report_email(
        self,
        report: WelfareReport,
        to_email: Optional[str] = None,
        cc_volunteers: bool = False,
    ) -> bool:
        """
        Send the report via email.

        NOTE: This is a placeholder implementation. In production, integrate
        with a real email service (e.g., AWS SES, SendGrid, or SMTP).
        """
        to_addr = to_email or settings.REPORT_EMAIL_TO

        if not to_addr:
            logger.warning("No recipient email configured. Report not sent.")
            return False

        # --- Production: Replace this with real SMTP/SES call ---
        logger.info(
            "📧 REPORT EMAIL (placeholder):\n"
            "  To: %s\n"
            "  From: %s\n"
            "  Subject: Welfare Report — %s [%s]\n"
            "  Body preview: %s",
            to_addr,
            settings.REPORT_EMAIL_FROM,
            report.senior_name,
            report.senior_id,
            report.raw_markdown[:200],
        )

        # --- Example SMTP implementation (uncomment in production) ---
        """
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(report.raw_markdown, "plain", "utf-8")
        msg["Subject"] = f"Welfare Report — {report.senior_name} [{report.senior_id}]"
        msg["From"] = settings.REPORT_EMAIL_FROM
        msg["To"] = to_addr

        if cc_volunteers and settings.HELPER_EMAIL:
            msg["Cc"] = settings.HELPER_EMAIL

        with smtplib.SMTP("smtp.example.com", 587) as server:
            server.starttls()
            server.login("your_email", "your_password")
            server.send_message(msg)
        """

        logger.info("Email notification dispatched to %s", to_addr)
        return True