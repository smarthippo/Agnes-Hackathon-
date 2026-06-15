"""
KampungKonekt FastAPI Application
HTTP API endpoints for the KampungKonekt backend.

Usage:
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure backend/ is on the path
_BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from api.agnes_client import AgnesClient
from models.schemas import (
    AgnesIngestionRequest,
    AgnesIngestionResponse,
    MemoryEntry,
    SentimentLabel,
    ConcernCategory,
    WelfareFlag,
)
from memory.storage import MemoryStorage
from analytics.detector import AnomalyDetector
from reports.generator import ReportGenerator
from main import KampungKonektOrchestrator, simulate_week_of_interactions, settings

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
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="KampungKonekt",
    description="Hyper-local welfare monitoring web app for elderly residents in Singapore",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class VoiceInputRequest(BaseModel):
    raw_text: str
    language_hint: str = "en"
    senior_id: Optional[str] = None

class WelfareCheckRequest(BaseModel):
    senior_id: str

class ReportRequest(BaseModel):
    senior_id: str
    days: int = 30

class WelfareCheckResponse(BaseModel):
    senior_id: str
    risk_level: str
    risk_description: str
    flags_triggered: int
    total_flags_all_time: int
    recent_interactions: int
    report_path: Optional[str] = None
    report_sentiment: Optional[dict] = None

class SimulationRequest(BaseModel):
    senior_id: Optional[str] = None

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "KampungKonekt",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }

@app.get("/health")
async def health_check():
    """Simple health check."""
    return {"status": "healthy"}

@app.post("/api/voice/process", response_model=dict)
async def process_voice_input(request: VoiceInputRequest):
    """
    Process a single voice interaction.
    
    Takes transcribed voice text from the senior, processes it through
    the Agnes API (or local fallback), stores the memory, and runs
    anomaly detection.
    """
    try:
        with KampungKonektOrchestrator() as orch:
            entry = orch.process_voice_input(
                raw_text=request.raw_text,
                senior_id=request.senior_id,
                language_hint=request.language_hint,
            )
            
            return {
                "success": True,
                "entry_id": entry.id,
                "raw_text": entry.raw_text,
                "translated_text": entry.translated_text,
                "detected_language": entry.detected_language,
                "sentiment": entry.sentiment.value,
                "sentiment_score": entry.sentiment_score,
                "concerns": [c.value for c in entry.concerns],
                "wellness_notes": entry.wellness_notes,
                "suggested_response": entry.suggested_response,
            }
    except Exception as e:
        logger.exception("Error processing voice input")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/welfare/check", response_model=WelfareCheckResponse)
async def run_welfare_check(request: WelfareCheckRequest):
    """
    Run a comprehensive welfare check for a senior.
    
    Performs anomaly detection, compiles flags, and generates a report
    if risk level is elevated.
    """
    try:
        with KampungKonektOrchestrator() as orch:
            result = orch.run_welfare_check(request.senior_id)
            
            return WelfareCheckResponse(
                senior_id=result["senior_id"],
                risk_level=result["risk_level"],
                risk_description=result["risk_description"],
                flags_triggered=result["flags_triggered"],
                total_flags_all_time=result["total_flags_all_time"],
                recent_interactions=result["recent_interactions"],
                report_path=result.get("report_path"),
                report_sentiment=result.get("report_sentiment"),
            )
    except Exception as e:
        logger.exception("Error running welfare check")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/report/generate")
async def generate_report(request: ReportRequest):
    """
    Generate a welfare report for a senior.
    
    Creates a markdown report with sentiment analysis, welfare flags,
    concerns timeline, and recommended actions.
    """
    try:
        with KampungKonektOrchestrator() as orch:
            report = orch._reporter.generate_welfare_report(
                senior_id=request.senior_id,
                days=request.days,
                force_red_flag=True,
            )
            
            if not report:
                raise HTTPException(status_code=400, detail="No report generated (no flags triggered).")
            
            output_path = _BACKEND_DIR / "reports" / f"welfare_{request.senior_id}_{datetime.now().strftime('%Y%m%d')}.md"
            orch._reporter.save_report(report, str(output_path))
            
            return {
                "success": True,
                "report_path": str(output_path),
                "raw_markdown": report.raw_markdown[:2000],
                "sentiment_summary": report.sentiment_summary,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generating report")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/simulate")
async def run_simulation(request: SimulationRequest):
    """
    Simulate a week of senior interactions for testing/demo.
    
    Processes 7 days of declining interactions and triggers welfare alerts.
    """
    try:
        senior_id = request.senior_id or settings.SENIOR_ID
        
        with KampungKonektOrchestrator() as orch:
            simulate_week_of_interactions(orch)
            
            result = orch.run_welfare_check(senior_id)
            
            return {
                "success": True,
                "message": "Simulation complete",
                "senior_id": senior_id,
                "result": result,
            }
    except Exception as e:
        logger.exception("Error running simulation")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/seniors/{senior_id}/entries")
async def get_senior_entries(senior_id: str, days: int = 30, limit: int = 50):
    """
    Get memory entries for a senior.
    
    Returns a list of past interactions with sentiment and concerns.
    """
    try:
        with KampungKonektOrchestrator() as orch:
            entries = orch._storage.get_entries(senior_id, days=days, limit=limit)
            
            return {
                "senior_id": senior_id,
                "count": len(entries),
                "entries": [
                    {
                        "id": e.id,
                        "timestamp": e.timestamp.isoformat(),
                        "raw_text": e.raw_text,
                        "translated_text": e.translated_text,
                        "sentiment": e.sentiment.value,
                        "sentiment_score": e.sentiment_score,
                        "concerns": [c.value for c in e.concerns],
                        "detected_language": e.detected_language,
                    }
                    for e in entries
                ],
            }
    except Exception as e:
        logger.exception("Error fetching entries")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/seniors/{senior_id}/flags")
async def get_senior_flags(senior_id: str, severity: Optional[str] = None):
    """
    Get welfare flags for a senior.
    
    Returns all triggered welfare alerts (red/yellow).
    """
    try:
        with KampungKonektOrchestrator() as orch:
            from analytics.detector import AlertSeverity
            
            sev_filter = None
            if severity:
                try:
                    sev_filter = AlertSeverity(severity)
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}. Must be 'red' or 'yellow'.")
            
            flags = orch._storage.get_flags(senior_id, severity=sev_filter)
            
            return {
                "senior_id": senior_id,
                "count": len(flags),
                "flags": [
                    {
                        "id": f.id,
                        "severity": f.severity.value,
                        "triggered_at": f.triggered_at.isoformat(),
                        "reason": f.reason,
                        "summary": f.summary,
                    }
                    for f in flags
                ],
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching flags")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/seniors/{senior_id}/summary")
async def get_senior_summary(senior_id: str, days: int = 30):
    """
    Get a summary of a senior's welfare status.
    
    Includes sentiment breakdown, concern counts, and risk level.
    """
    try:
        with KampungKonektOrchestrator() as orch:
            sentiment_summary = orch._storage.get_sentiment_summary(senior_id, days=days)
            concern_summary = orch._storage.get_concern_summary(senior_id, days=days)
            total_interactions = orch._storage.get_total_interaction_count(senior_id, days=days)
            risk_level, risk_desc = orch._detector.get_risk_level(senior_id)
            
            return {
                "senior_id": senior_id,
                "period_days": days,
                "total_interactions": total_interactions,
                "sentiment_summary": sentiment_summary,
                "concern_summary": concern_summary,
                "current_risk_level": risk_level.value,
                "risk_description": risk_desc,
            }
    except Exception as e:
        logger.exception("Error fetching senior summary")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Startup/Shutdown Events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    logger.info("KampungKonekt API server starting up")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("KampungKonekt API server shutting down")