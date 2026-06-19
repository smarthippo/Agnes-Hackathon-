"""
KampungKonekt FastAPI Server
Exposes the backend pipeline as HTTP endpoints for the frontend.

Run:
    cd backend
    uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import sys
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
app = FastAPI(title="KampungKonekt API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


class UserCreate(BaseModel):
    name: str
    contact_name: str
    contact_number: str
    language: str = "en"
    health_notes: str = ""


class UserUpdate(BaseModel):
    name: str
    contact_name: str
    contact_number: str
    language: str = "en"
    health_notes: str = ""


class CallFamilyRequest(BaseModel):
    language: str = "en"
    user_name: Optional[str] = None


class CallFamilyResponse(BaseModel):
    success: bool
    message_sent: str
    contact_number: str
    whatsapp_url: str


class TTSRequest(BaseModel):
    text: str
    language: str = "en"  # "en", "zh", or "ms"


class LoginRequest(BaseModel):
    name: str
    language: Optional[str] = None


class LoginResponse(BaseModel):
    id: int
    name: str
    contact_name: str
    contact_number: str
    language: str
    health_notes: str
    created_at: str


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

    # Immediate risk override: escalate based on THIS message's concerns,
    # regardless of historical DB state (so first-time mentions still trigger alerts).
    from models.schemas import AlertSeverity, ConcernCategory
    IMMEDIATE_RED    = {ConcernCategory.DEPRESSION_SIGNS}
    IMMEDIATE_YELLOW = {ConcernCategory.PHYSICAL_PAIN, ConcernCategory.MEDICATION_ISSUES}
    current_concerns = set(agnes_resp.concerns)
    if current_concerns & IMMEDIATE_RED:
        risk_level = AlertSeverity.RED
    elif (current_concerns & IMMEDIATE_YELLOW) and risk_level.value == "green":
        risk_level = AlertSeverity.YELLOW

    # Draft caregiver alert if any flags triggered OR immediate concerns detected
    alert_message = None
    if flags or current_concerns:
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
        flags_triggered=len(flags) or len(current_concerns),
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
# Auth — Login
# ---------------------------------------------------------------------------

@app.post("/api/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """Look up a user by name. Saves language preference if provided. Returns profile."""
    user = _storage.get_user(req.name.strip())
    if not user:
        raise HTTPException(status_code=404, detail="No profile found. Please register first.")
    if req.language:
        _storage.save_user_language(req.name.strip(), req.language)
        user["language"] = req.language
    return user


@app.get("/api/history/{senior_id}")
def get_user_history(senior_id: str):
    """Return the last 5 interactions for a senior, formatted for Gemini context."""
    return {"history": _storage.get_user_history_for_ai(senior_id, last_n=5)}


# ---------------------------------------------------------------------------
# User routes (CRUD)
# ---------------------------------------------------------------------------

@app.get("/users")
def list_users():
    return _storage.get_all_users()


@app.post("/users", status_code=201)
def create_user(body: UserCreate):
    try:
        user = _storage.create_user(
            body.name.strip(), body.contact_name.strip(), body.contact_number.strip(),
            body.language, body.health_notes.strip(),
        )
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
        user = _storage.update_user(
            name, body.name.strip(), body.contact_name.strip(), body.contact_number.strip(),
            body.language, body.health_notes.strip(),
        )
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


# ---------------------------------------------------------------------------
# Call Family — WhatsApp deep link
# ---------------------------------------------------------------------------

@app.post("/api/call-family", response_model=CallFamilyResponse)
def call_family(req: CallFamilyRequest):
    """Compose a pre-filled WhatsApp message to the user's emergency contact."""
    import datetime
    import urllib.parse

    # Pull profile from DB if a user_name was provided, else fall back to settings
    profile = _storage.get_user(req.user_name) if req.user_name else None
    senior_name = profile["name"] if profile else settings.SENIOR_NAME
    contact = profile["contact_number"] if profile else getattr(settings, "EMERGENCY_CONTACT", "")
    now = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")

    if req.language == "zh":
        message = (
            f"【KampungKonekt 通知】{now}\n\n"
            f"{senior_name} 刚刚通过 KampungKonekt 应用联系了您。"
            f"请尽快致电或探访，确认她的情况。\n\n"
            f"如有紧急情况，请拨打 995。"
        )
    elif req.language == "ms":
        message = (
            f"[KampungKonekt] {now}\n\n"
            f"{senior_name} baru sahaja menghubungi anda melalui aplikasi KampungKonekt. "
            f"Sila hubungi atau lawati beliau secepat mungkin.\n\n"
            f"Hubungi 995 sekiranya kecemasan."
        )
    else:
        message = (
            f"[KampungKonekt] {now}\n\n"
            f"{senior_name} has reached out via the KampungKonekt app. "
            f"Please call or visit her as soon as possible to check she is okay.\n\n"
            f"Call 995 for emergencies."
        )

    # Build wa.me link — Singapore numbers: prepend 65
    phone = contact.replace(" ", "").replace("-", "").lstrip("+").lstrip("0")
    if not phone.startswith("65"):
        phone = "65" + phone

    whatsapp_url = f"https://wa.me/{phone}?text={urllib.parse.quote(message)}"
    logger.info("WhatsApp link generated for %s → %s", senior_name, phone)

    return CallFamilyResponse(
        success=True,
        message_sent=message,
        contact_number=contact,
        whatsapp_url=whatsapp_url,
    )


# ---------------------------------------------------------------------------
# Text-to-Speech
# ---------------------------------------------------------------------------

@app.post("/api/tts")
def text_to_speech(req: TTSRequest):
    """Convert text to speech audio using gTTS. Returns MP3 audio bytes."""
    from gtts import gTTS
    import io
    from fastapi.responses import StreamingResponse

    lang_map = {"en": "en", "zh": "zh-CN", "ms": "ms"}
    gtts_lang = lang_map.get(req.language, "en")

    tts = gTTS(text=req.text, lang=gtts_lang, slow=False)
    audio_buffer = io.BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)

    return StreamingResponse(audio_buffer, media_type="audio/mpeg")


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

_FRONTEND = _BACKEND_DIR.parent / "index.html"
_CONFIG_JS = _BACKEND_DIR.parent / "config.js"
_MUSIC_DIR = _BACKEND_DIR.parent / "music"

# Serve music files as static
if _MUSIC_DIR.exists():
    app.mount("/music", StaticFiles(directory=str(_MUSIC_DIR)), name="music")

@app.get("/")
def serve_frontend():
    if _FRONTEND.exists():
        return FileResponse(str(_FRONTEND))
    raise HTTPException(status_code=404, detail="Frontend not found")

@app.get("/config.js")
def serve_config():
    if _CONFIG_JS.exists():
        return FileResponse(str(_CONFIG_JS), media_type="application/javascript")
    # Return empty config if file doesn't exist
    from fastapi.responses import Response
    return Response(content="const FRONTEND_CONFIG = {};", media_type="application/javascript")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
