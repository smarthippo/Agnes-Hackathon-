"""
<<<<<<< HEAD
KampungKonekt FastAPI Server
Exposes the backend pipeline as HTTP endpoints for the frontend.

Run:
    cd backend
=======
KampungKonekt API Server
FastAPI server exposing user CRUD and welfare pipeline endpoints.

Run with:
>>>>>>> source-repo/main
    uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import sys
<<<<<<< HEAD
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Ensure backend/ is on path
_BACKEND_DIR = Path(__file__).parent
sys.path.insert(0, str(_BACKEND_DIR))

from api.agnes_client import AgnesClient
from memory.storage import MemoryStorage
from analytics.detector import AnomalyDetector
from reports.generator import ReportGenerator
from models.schemas import AgnesIngestionRequest
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("KampungKonekt.Server")

=======
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from memory.storage import MemoryStorage
from config.settings import settings

>>>>>>> source-repo/main
app = FastAPI(title="KampungKonekt API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

<<<<<<< HEAD
# Shared instances (initialized on startup)
_storage: Optional[MemoryStorage] = None
_agnes: Optional[AgnesClient] = None
_detector: Optional[AnomalyDetector] = None
_reporter: Optional[ReportGenerator] = None


@app.on_event("startup")
def startup():
    global _storage, _agnes, _detector, _reporter
    _storage = MemoryStorage(db_path=settings.DB_PATH)
    _agnes = AgnesClient()
    _detector = AnomalyDetector(_storage)
    _reporter = ReportGenerator(_storage)
    logger.info("Server started for senior: %s (%s)", settings.SENIOR_NAME, settings.SENIOR_ID)


@app.on_event("shutdown")
def shutdown():
    if _storage:
        _storage.close()


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class ProcessRequest(BaseModel):
    text: str
    language: str = "en"
    senior_id: Optional[str] = None


class ProcessResponse(BaseModel):
    translated_text: str
    sentiment: str
    sentiment_score: float
    concerns: list[str]
    wellness_notes: str
    suggested_response: str
    detected_language: str
    flags_triggered: int
    risk_level: str
    alert_message: Optional[str] = None


class StatusResponse(BaseModel):
    senior_id: str
    senior_name: str
    risk_level: str
    risk_description: str
    recent_interactions: int
    sentiment_summary: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/process", response_model=ProcessResponse)
def process_voice(req: ProcessRequest):
    """Process a voice/text input from the senior and return AI analysis."""
    target_id = req.senior_id or settings.SENIOR_ID

    agnes_req = AgnesIngestionRequest(
        raw_text=req.text,
        senior_id=target_id,
        language_hint=req.language,
        context=_storage.get_recent_context(target_id, last_n=3),
    )
    agnes_resp = _agnes.ingest(agnes_req)

    from models.schemas import MemoryEntry
    entry = MemoryEntry(
        senior_id=target_id,
        raw_text=req.text,
        detected_language=agnes_resp.detected_language,
        translated_text=agnes_resp.translated_text,
        sentiment=agnes_resp.sentiment,
        sentiment_score=agnes_resp.sentiment_score,
        concerns=agnes_resp.concerns,
        concern_details=agnes_resp.concern_details,
        wellness_notes=agnes_resp.wellness_notes,
        suggested_response=agnes_resp.suggested_response,
    )
    _storage.insert_entry(entry)

    flags = _detector.run_full_check(target_id)
    for flag in flags:
        _storage.insert_flag(flag)

    # Auto-generate report on red flag
    red_flags = [f for f in flags if f.severity.value == "red"]
    if red_flags:
        report = _reporter.generate_welfare_report(
            senior_id=target_id, days=30, force_red_flag=True
        )
        if report:
            out = _BACKEND_DIR / "reports" / f"welfare_{target_id}_latest.md"
            _reporter.save_report(report, str(out))

    risk_level, _ = _detector.get_risk_level(target_id)

    # Draft caregiver alert if any flags triggered
    alert_message = None
    if flags:
        alert_message = _agnes.draft_caregiver_alert(
            senior_name=settings.SENIOR_NAME,
            raw_text=req.text,
            concerns=agnes_resp.concerns,
            flags_count=len(flags),
            lang=req.language,
        )

    return ProcessResponse(
        translated_text=agnes_resp.translated_text,
        sentiment=agnes_resp.sentiment.value,
        sentiment_score=agnes_resp.sentiment_score,
        concerns=[c.value for c in agnes_resp.concerns],
        wellness_notes=agnes_resp.wellness_notes,
        suggested_response=agnes_resp.suggested_response,
        detected_language=agnes_resp.detected_language,
        flags_triggered=len(flags),
        risk_level=risk_level.value,
        alert_message=alert_message,
    )


@app.get("/api/status/{senior_id}", response_model=StatusResponse)
def get_status(senior_id: str):
    """Get current welfare status for a senior."""
    risk_level, risk_desc = _detector.get_risk_level(senior_id)
    sentiment_summary = _storage.get_sentiment_summary(senior_id, days=30)
    recent = _storage.get_total_interaction_count(senior_id, days=30)

    return StatusResponse(
        senior_id=senior_id,
        senior_name=settings.SENIOR_NAME,
        risk_level=risk_level.value,
        risk_description=risk_desc,
        recent_interactions=recent,
        sentiment_summary=sentiment_summary,
    )


@app.get("/api/status")
def get_default_status():
    return get_status(settings.SENIOR_ID)


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

_FRONTEND = _BACKEND_DIR.parent / "index.html"
_MUSIC_DIR = _BACKEND_DIR.parent / "music"

# Serve music files as static
if _MUSIC_DIR.exists():
    app.mount("/music", StaticFiles(directory=str(_MUSIC_DIR)), name="music")

@app.get("/")
def serve_frontend():
    if _FRONTEND.exists():
        return FileResponse(str(_FRONTEND))
    raise HTTPException(status_code=404, detail="Frontend not found")
=======
_storage = MemoryStorage(db_path=settings.DB_PATH)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    name: str
    contact_name: str
    contact_number: str


class UserUpdate(BaseModel):
    name: str
    contact_name: str
    contact_number: str


# ---------------------------------------------------------------------------
# User routes
# ---------------------------------------------------------------------------

@app.post("/users", status_code=201)
def create_user(body: UserCreate):
    try:
        user = _storage.create_user(body.name.strip(), body.contact_name.strip(), body.contact_number.strip())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return user


@app.get("/users/{name}")
def get_user(name: str):
    user = _storage.get_user(name)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@app.put("/users/{name}")
def update_user(name: str, body: UserUpdate):
    try:
        user = _storage.update_user(name, body.name.strip(), body.contact_name.strip(), body.contact_number.strip())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@app.delete("/users/{name}", status_code=204)
def delete_user(name: str):
    deleted = _storage.delete_user(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found.")
>>>>>>> source-repo/main
