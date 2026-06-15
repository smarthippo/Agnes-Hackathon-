"""
Agnes Text API Client
Handles all communication with the Agnes backend for:
  - Dialect-aware translation (Hokkien, Teochew, Singlish, Malay, Mandarin)
  - Sentiment analysis
  - Welfare concern extraction
  - Suggested conversational responses

This module supports both a real API call (via HTTP) and a graceful
fallback mock mode so the pipeline can be tested offline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import httpx
from pydantic import ValidationError as PydanticValidationError

from config.settings import settings
from models.schemas import (
    AgnesIngestionRequest,
    AgnesIngestionResponse,
    ConcernCategory,
    SentimentLabel,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local dialect lexicon for fallback / hybrid processing
# ---------------------------------------------------------------------------

# Hokrien -> English mappings (common phrases)
_HOKKIEN_PHRASES: dict[str, str] = {
    "bo lang cai gia": "Nobody cooks for me today",
    "bo liao cai gia": "Nobody has cooked for me",
    "bo u lang tsai": "No one is here with me",
    "sui mna ta": "I don't want to eat",
    "ka kae bo lei": "No one comes to visit",
    "xin li mna ka": "My heart hurts (I'm sad)",
    "u lei sai mna ka": "I don't have anyone to talk to",
    "kong lo bo lei ia": "Talking to the air, no one listens",
    "sim buey nang ia": "Feel like crying",
    "seng kiu bo lei tsai": "Living here, no one stays with me",
}

# Teochew -> English mappings (common phrases)
_TEOTREW_PHRASES: dict[str, str] = {
    "bo ing ua a": "Nobody's around",
    "gua buee su": "I'm very tired",
    "gua mna eh ua": "I don't want (to do) it",
    "su a gu a": "Please help me",
    "gua ia su a": "I need help",
}

# Malay welfare-relevant phrases
_MALAY_PHRASES: dict[str, str] = {
    "sakit hati": "Heartache / deep sadness",
    "sakit kepala": "Headache",
    "sakit badan": "Body ache",
    "takde nak makan": "No desire to eat",
    "sendiri saja": "All alone",
    "takde orang jaga": "No one to take care of me",
    "penat pula": "Feeling weary",
    "rindu anak cucu": "Miss my children and grandchildren",
    "nak balik rumah": "Want to go home",
}

# Mandarin welfare-relevant phrases
_MANDARIN_PHRASES: dict[str, str] = {
    "我一个人": "I am alone",
    "没有人陪我": "No one keeps me company",
    "我不想吃饭": "I don't want to eat",
    "我很孤独": "I am very lonely",
    "我头痛": "I have a headache",
    "我心痛": "I have chest pain / heartache",
    "我脚痛": "My feet hurt",
    "我睡不着": "I can't sleep",
    "我想我的孩子": "I miss my children",
    "没人在乎我": "Nobody cares about me",
}


class AgnesClientError(Exception):
    """Raised when the Agnes API returns an unrecoverable error."""


class AgnesClient:
    """
    Client for the Agnes Text API.

    Usage:
        client = AgnesClient()
        response = await client.ingest(raw_text="Bo lang cai gia", senior_id="s1")
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None) -> None:
        self._api_key = api_key or settings.AGNES_API_KEY
        self._base_url = (base_url or settings.AGNES_API_BASE_URL).rstrip("/")
        self._http = httpx.Client(
            base_url=self._base_url,
            timeout=15.0,
            headers={
                "Authorization": f"Bearer {self._api_key}" if self._api_key else "",
                "Content-Type": "application/json",
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(self, request: AgnesIngestionRequest) -> AgnesIngestionResponse:
        """
        Send raw text to Agnes for contextual processing.

        Falls back to local dialect lexicon + keyword analysis if the API
        is unavailable (mock mode).
        """
        try:
            return self._call_agnes_api(request)
        except httpx.HTTPError as exc:
            logger.warning(
                "Agnes API call failed (%s). Falling back to local processing.", exc
            )
            return self._local_fallback(request)
        except PydanticValidationError as exc:
            logger.warning("Agnes API validation error (%s). Falling back.", exc)
            return self._local_fallback(request)

    # ------------------------------------------------------------------
    # Real API call
    # ------------------------------------------------------------------

    def _call_agnes_api(
        self, request: AgnesIngestionRequest
    ) -> AgnesIngestionResponse:
        payload = request.model_dump(exclude_none=True)
        response = self._http.post("/ingest", json=payload)
        response.raise_for_status()
        data = response.json()

        # Parse language hint from Agnes response
        detected_lang = data.get("detected_language", request.language_hint or "en")

        return AgnesIngestionResponse(
            translated_text=data.get("translated_text", request.raw_text),
            sentiment=SentimentLabel(data.get("sentiment", "neutral")),
            sentiment_score=float(data.get("sentiment_score", 0.5)),
            concerns=[
                ConcernCategory(c) for c in data.get("concerns", [])
            ],
            concern_details=data.get("concern_details", []),
            wellness_notes=data.get("wellness_notes", ""),
            suggested_response=data.get("suggested_response", ""),
            detected_language=detected_lang,
        )

    # ------------------------------------------------------------------
    # Local Fallback — dialect lexicon + keyword analysis
    # ------------------------------------------------------------------

    def _local_fallback(
        self, request: AgnesIngestionRequest
    ) -> AgnesIngestionResponse:
        """
        Fallback processing when the real Agnes API is unavailable.
        Uses local lexicons and keyword matching to simulate Agnes output.
        """
        raw = request.raw_text.lower().strip()

        # --- Step 1: Try dialect lexicon match ---
        translated = self._match_dialect(raw)
        detected_lang = self._detect_language(raw)

        # --- Step 2: Sentiment analysis (keyword-based) ---
        sentiment, score = self._analyze_sentiment(raw)

        # --- Step 3: Welfare concern extraction ---
        concerns, details = self._extract_concerns(raw, request)

        # --- Step 4: Wellness notes ---
        wellness_notes = self._generate_wellness_notes(sentiment, concerns, details)

        # --- Step 5: Suggested response ---
        suggested = self._generate_suggested_response(sentiment, concerns)

        logger.info(
            "Local fallback: sentiment=%s concerns=%s lang=%s",
            sentiment.value,
            [c.value for c in concerns],
            detected_lang,
        )

        return AgnesIngestionResponse(
            translated_text=translated,
            sentiment=sentiment,
            sentiment_score=score,
            concerns=concerns,
            concern_details=details,
            wellness_notes=wellness_notes,
            suggested_response=suggested,
            detected_language=detected_lang,
        )

    # ------------------------------------------------------------------
    # Dialect matching helpers
    # ------------------------------------------------------------------

    def _match_dialect(self, raw: str) -> str:
        """Try to find a dialect phrase match and return English translation."""
        # Check Hokkien
        for phrase, translation in _HOKKIEN_PHRASES.items():
            if phrase in raw:
                return f"[Hokkien] {translation}"

        # Check Teochew
        for phrase, translation in _TEOTREW_PHRASES.items():
            if phrase in raw:
                return f"[Teochew] {translation}"

        # Check Malay
        for phrase, translation in _MALAY_PHRASES.items():
            if phrase in raw:
                return f"[Malay] {translation}"

        # Check Mandarin (substring match)
        for phrase, translation in _MANDARIN_PHRASES.items():
            if phrase in raw:
                return f"[Mandarin] {translation}"

        # No dialect match — return original with hint
        return f"[Direct] {raw}"

    def _detect_language(self, raw: str) -> str:
        """Best-effort language detection based on keyword presence."""
        # Check Hokkien (common characters and phrases)
        hokkien_markers = ["bo ", "gia", "tsai", "buey", "sioh", "ka kae"]
        for m in hokkien_markers:
            if m in raw:
                return "hak"

        # Check Teochew
        teochew_markers = ["ing ", "gua ", "ua", "gwa"]
        for m in teochew_markers:
            if m in raw:
                return "tdd"

        # Check Mandarin (CJK characters)
        if any("\u4e00" <= c <= "\u9fff" for c in raw):
            return "zh"

        # Check Malay (common words)
        malay_markers = ["sakit", "takde", "sendiri", "penat", "rindu", "nak"]
        for m in malay_markers:
            if m in raw:
                return "ms"

        # Default to English / Singlish
        return "en"

    # ------------------------------------------------------------------
    # Sentiment analysis
    # ------------------------------------------------------------------

    def _analyze_sentiment(
        self, raw: str
    ) -> tuple[SentimentLabel, float]:
        """Keyword-based sentiment analysis."""
        positive_words = [
            "happy", "good", "fine", "great", "thank", "blessing",
            "alhamdulillah", "thanks", "joyful", "comfortable", "ok lah",
        ]
        negative_words = [
            "sad", "lonely", "alone", "pain", "hurt", "hungry",
            "tired", "die", "cannot", "no one", "nobody", "cry",
            "sakit", "send li", "bo lang", "sioh", "no point",
        ]

        pos_count = sum(1 for w in positive_words if w in raw)
        neg_count = sum(1 for w in negative_words if w in raw)

        total = pos_count + neg_count
        if total == 0:
            return SentimentLabel.NEUTRAL, 0.5

        if neg_count > pos_count:
            score = neg_count / total
            return SentimentLabel.NEGATIVE, round(0.5 + score * 0.5, 2)
        elif pos_count > neg_count:
            score = pos_count / total
            return SentimentLabel.POSITIVE, round(0.5 + score * 0.5, 2)
        else:
            return SentimentLabel.NEUTRAL, 0.5

    # ------------------------------------------------------------------
    # Welfare concern extraction
    # ------------------------------------------------------------------

    def _extract_concerns(
        self,
        raw: str,
        request: AgnesIngestionRequest,
    ) -> tuple[list[ConcernCategory], list[dict]]:
        """Identify welfare concerns from the raw text."""
        concerns: list[ConcernCategory] = []
        details: list[dict] = []

        for category, keywords in settings.WELFARE_CONCERNS.items():
            matched = [kw for kw in keywords if kw.lower() in raw.lower()]
            if matched:
                cat = ConcernCategory(category)
                concerns.append(cat)
                details.append({
                    "category": category,
                    "matched_phrases": matched,
                    "severity": "high" if len(matched) >= 2 else "medium",
                })

        return concerns, details

    # ------------------------------------------------------------------
    # Response generation helpers
    # ------------------------------------------------------------------

    def _generate_wellness_notes(
        self,
        sentiment: SentimentLabel,
        concerns: list[ConcernCategory],
        details: list[dict],
    ) -> str:
        """Generate a plain-language wellness summary."""
        if sentiment == SentimentLabel.POSITIVE:
            return "Senior appears in a good mood today. No immediate welfare concerns detected."

        concern_strs = [f"- {d['category']}: {'; '.join(d['matched_phrases'])}" for d in details]
        note = f"Senior expressed {sentiment.value} sentiment ({len(concerns)} concern(s) identified):\n" + "\n".join(concern_strs)
        return note

    def _generate_suggested_response(
        self,
        sentiment: SentimentLabel,
        concerns: list[ConcernCategory],
    ) -> str:
        """Generate a friendly, culturally-aware response for the senior."""
        if sentiment == SentimentLabel.POSITIVE:
            return "That's wonderful to hear! 😊 Is there anything else you'd like to share?"

        if ConcernCategory.FOOD_INSECURITY in concerns:
            return "I hear you. Let me note that you haven't had proper meals. Would you like me to arrange a community lunch visit for you? 🍜"

        if ConcernCategory.LONELINESS in concerns:
            return "It's okay to feel that way. You're not alone — I'm always here to talk. Would you like me to arrange a visit from a volunteer? 👋"

        if ConcernCategory.PHYSICAL_PAIN in concerns:
            return "I'm sorry you're in pain. Please make sure to take your medicine. Should I let your helper know about this? 🏥"

        if ConcernCategory.DEPRESSION_SIGNS in concerns:
            return "Thank you for sharing how you feel. Your feelings are valid. Let me inform your helper so they can check on you soon. 💚"

        return "Thank you for telling me. I've noted everything down. Is there anything else on your mind? 💬"