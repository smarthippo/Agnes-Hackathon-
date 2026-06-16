"""
KampungKonekt Settings Module
Loads and validates configuration from .env file and defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
_PROJECT_ROOT = Path(__file__).parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


def _get_env(key: str, default: str = "") -> str:
    """Safely read an environment variable."""
    return os.getenv(key, default).strip()


def _get_int(key: str, default: int = 0) -> int:
    """Safely read an integer environment variable."""
    raw = _get_env(key, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


class Settings:
    """Centralized settings for KampungKonekt backend."""

    # --- Gemini (STT + dialect understanding) ---
    GEMINI_API_KEY: str = _get_env("GEMINI_API_KEY")


    # --- Agnes API ---
    AGNES_API_KEY: str = _get_env("AGNES_API_KEY")
    AGNES_API_BASE_URL: str = _get_env(
        "AGNES_API_BASE_URL", "https://api.agnes.example.com/v1"
    )

    # --- Database ---
    DB_PATH: str = _get_env("DB_PATH", str(_PROJECT_ROOT / "data" / "kampungkonekt.db"))

    # --- Welfare Alert Thresholds ---
    SENTIMENT_CONSECUTIVE_THRESHOLD: int = _get_int(
        "SENTIMENT_CONSECUTIVE_THRESHOLD", 3
    )

    # --- Email Reporting (placeholder — use SMTP in production) ---
    REPORT_EMAIL_TO: str = _get_env("REPORT_EMAIL_TO")
    REPORT_EMAIL_FROM: str = _get_env("REPORT_EMAIL_FROM", "kampungkonekt@system.local")

    # --- Senior Profile ---
    SENIOR_ID: str = _get_env("SENIOR_ID", "senior_001")
    SENIOR_NAME: str = _get_env("SENIOR_NAME", "Grandma Lim")
    EMERGENCY_CONTACT: str = _get_env("EMERGENCY_CONTACT", "91234567")
    HELPER_NAME: str = _get_env("HELPER_NAME", "Sarah")
    HELPER_EMAIL: str = _get_env("HELPER_EMAIL")

    # --- Supported Languages / Dialects ---
    SUPPORTED_LANGUAGES: list[str] = [
        "en",  # English
        "si",  # Singlish (mapped to English with dialect hints)
        "ms",  # Malay
        "zh",  # Mandarin
        "hak",  # Hokkien
        "tdd",  # Teochew
    ]

    # --- Welfare Concern Keywords ---
    WELFARE_CONCERNS = {
        "loneliness": [
            "alone", "lonely", "no one", "nobody", "send li", "want family",
            "bo lang cai gia", "bo liao cai gia", "nobody home", "by myself",
            "no company", "no friend", "no family",
        ],
        "food_insecurity": [
            "no food", "don't eat", "didn't eat", "haven't eaten", "hungry",
            "bo lang cai gia", "can't cook", "nobody cook", "nothing to eat",
            "skip meal", "missed lunch", "no appetite", "cannot eat",
        ],
        "physical_pain": [
            "pain", "hurt", "hurting", "aches", "aching", "sakit", "sioh",
            "头昏", "脚痛", "心痛", "dizzy", "cannot walk", "fall", "跌",
            "diarrhea", "diarrhoea", "vomit", "nausea", "fever", "sick",
            "not feeling well", "unwell", "headache", "chest pain", "stomach",
            "not well", "feeling ill", "feeling sick", "flu", "cough", "weak",
        ],
        "medication_issues": [
            "medicine", "pills", "tablet", "medication", "take medicine",
            "sakit", "did not take", "miss pill", "forgot medicine",
        ],
        "depression_signs": [
            "no point", "want die", "want to die", "going to die", "die soon",
            "cannot live", "no reason to live", "give up", "end it",
            "tired of living", "no energy", "everything useless", "sakit hati",
            "sad", "cry every day", "hopeless", "worthless", "don't want to live",
            "dying", "die", "death", "kill myself", "not worth living",
        ],
    }


# Singleton instance
settings = Settings()