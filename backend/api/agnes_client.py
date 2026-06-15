"""
Agnes AI Client
Handles communication with Agnes AI (https://apihub.agnes-ai.com/v1)
for dialect-aware text understanding, sentiment analysis, and welfare concern extraction.

Falls back to local keyword processing if the API is unavailable.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

from config.settings import settings
from models.schemas import (
    AgnesIngestionRequest,
    AgnesIngestionResponse,
    ConcernCategory,
    SentimentLabel,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local dialect lexicon for fallback processing
# ---------------------------------------------------------------------------

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

_TEOTREW_PHRASES: dict[str, str] = {
    "bo ing ua a": "Nobody's around",
    "gua buee su": "I'm very tired",
    "gua mna eh ua": "I don't want (to do) it",
    "su a gu a": "Please help me",
    "gua ia su a": "I need help",
}

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

# ---------------------------------------------------------------------------
# System prompt for Agnes
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_EN = """You are a welfare analysis assistant for KampungKonekt, a senior care app in Singapore.

You will receive speech from elderly Singaporean seniors. They may speak in English, Singlish, Malay, Mandarin, Hokkien, Teochew, or a mix of these languages.

Analyze the text and respond ONLY with a valid JSON object in this exact format:
{
  "translated_text": "<English translation of what was said, or the original if already in English>",
  "detected_language": "<en|ms|zh|si|hak|tdd>",
  "sentiment": "<positive|neutral|negative>",
  "sentiment_score": <0.0 to 1.0>,
  "concerns": ["<concern_category>"],
  "concern_details": [{"category": "<name>", "matched_phrases": ["<phrase>"], "severity": "<high|medium>"}],
  "wellness_notes": "<brief welfare summary in English>",
  "suggested_response": "<warm, culturally appropriate response to say back to the senior IN ENGLISH>"
}

Valid concern categories: loneliness, food_insecurity, physical_pain, medication_issues, depression_signs
If no concerns, use empty arrays.
Respond ONLY with the JSON, no explanation, no markdown."""

_SYSTEM_PROMPT_ZH = """你是新加坡邻里关怀应用 KampungKonekt 的福利分析助手。

你将收到新加坡年长者说的话。他们可能用华语、方言（福建话、潮州话）、英语、马来语或混合语言说话。

请分析文本，并且只用以下 JSON 格式回复：
{
  "translated_text": "<将所说内容翻译成中文，如果已经是中文则保持原文>",
  "detected_language": "<en|ms|zh|si|hak|tdd>",
  "sentiment": "<positive|neutral|negative>",
  "sentiment_score": <0.0到1.0之间的数字>,
  "concerns": ["<关怀类别>"],
  "concern_details": [{"category": "<名称>", "matched_phrases": ["<词句>"], "severity": "<high|medium>"}],
  "wellness_notes": "<简短的福利摘要，用中文>",
  "suggested_response": "<用温暖、贴心的中文回应长者，要有文化关怀感>"
}

有效的关怀类别: loneliness, food_insecurity, physical_pain, medication_issues, depression_signs
如果没有关怀问题，使用空数组。
只回复 JSON，不要解释，不要用 markdown。"""


_SYSTEM_PROMPT_MS = """Anda adalah pembantu analisis kebajikan untuk KampungKonekt, aplikasi penjagaan warga emas di Singapura.

Anda akan menerima pertuturan daripada warga emas Singapura. Mereka mungkin bercakap dalam Bahasa Melayu, bahasa Inggeris, dialek, atau campuran bahasa-bahasa ini.

Analisis teks dan balas HANYA dengan objek JSON dalam format berikut:
{
  "translated_text": "<terjemahan dalam Bahasa Melayu, atau teks asal jika sudah dalam Bahasa Melayu>",
  "detected_language": "<en|ms|zh|si|hak|tdd>",
  "sentiment": "<positive|neutral|negative>",
  "sentiment_score": <0.0 hingga 1.0>,
  "concerns": ["<kategori_kebajikan>"],
  "concern_details": [{"category": "<nama>", "matched_phrases": ["<frasa>"], "severity": "<high|medium>"}],
  "wellness_notes": "<ringkasan kebajikan ringkas dalam Bahasa Melayu>",
  "suggested_response": "<respons yang mesra dan sesuai budaya kepada warga emas DALAM BAHASA MELAYU>"
}

Kategori kebajikan yang sah: loneliness, food_insecurity, physical_pain, medication_issues, depression_signs
Jika tiada kebimbangan, gunakan tatasusunan kosong.
Balas HANYA dengan JSON, tiada penjelasan, tiada markdown."""


class AgnesClient:
    """Client for Agnes AI API (OpenAI-compatible chat completions)."""

    def __init__(self) -> None:
        self._api_key = settings.AGNES_API_KEY
        self._base_url = settings.AGNES_API_BASE_URL.rstrip("/")
        self._http = httpx.Client(
            timeout=8.0,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    def ingest(self, request: AgnesIngestionRequest) -> AgnesIngestionResponse:
        """Send text to Agnes for welfare analysis. Falls back to local processing on error."""
        try:
            return self._call_agnes(request)
        except Exception as exc:
            logger.warning("Agnes API failed (%s). Using local fallback.", exc)
            return self._local_fallback(request)

    # ------------------------------------------------------------------
    # Agnes API call
    # ------------------------------------------------------------------

    def _call_agnes(self, request: AgnesIngestionRequest) -> AgnesIngestionResponse:
        if request.language_hint == "zh":
            system_prompt = _SYSTEM_PROMPT_ZH
        elif request.language_hint == "ms":
            system_prompt = _SYSTEM_PROMPT_MS
        else:
            system_prompt = _SYSTEM_PROMPT_EN
        payload = {
            "model": "agnes-2.0-flash",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.raw_text},
            ],
            "temperature": 0.2,
        }

        response = self._http.post(f"{self._base_url}/chat/completions", json=payload)
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        data = json.loads(content)

        concerns = []
        for c in data.get("concerns", []):
            try:
                concerns.append(ConcernCategory(c))
            except ValueError:
                pass

        return AgnesIngestionResponse(
            translated_text=data.get("translated_text", request.raw_text),
            sentiment=SentimentLabel(data.get("sentiment", "neutral")),
            sentiment_score=float(data.get("sentiment_score", 0.5)),
            concerns=concerns,
            concern_details=data.get("concern_details", []),
            wellness_notes=data.get("wellness_notes", ""),
            suggested_response=data.get("suggested_response", "Thank you for sharing. 😊"),
            detected_language=data.get("detected_language", "en"),
        )

    # ------------------------------------------------------------------
    # Local fallback
    # ------------------------------------------------------------------

    def _local_fallback(self, request: AgnesIngestionRequest) -> AgnesIngestionResponse:
        raw = request.raw_text.lower().strip()
        translated = self._match_dialect(raw)
        detected_lang = self._detect_language(raw)
        sentiment, score = self._analyze_sentiment(raw)
        concerns, details = self._extract_concerns(raw, request)
        wellness_notes = self._generate_wellness_notes(sentiment, concerns, details)
        suggested = self._generate_suggested_response(sentiment, concerns, lang=request.language_hint or "en")

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

    def _match_dialect(self, raw: str) -> str:
        for phrase, translation in _HOKKIEN_PHRASES.items():
            if phrase in raw:
                return f"[Hokkien] {translation}"
        for phrase, translation in _TEOTREW_PHRASES.items():
            if phrase in raw:
                return f"[Teochew] {translation}"
        for phrase, translation in _MALAY_PHRASES.items():
            if phrase in raw:
                return f"[Malay] {translation}"
        for phrase, translation in _MANDARIN_PHRASES.items():
            if phrase in raw:
                return f"[Mandarin] {translation}"
        return f"[Direct] {raw}"

    def _detect_language(self, raw: str) -> str:
        import re
        def word_in(word, text):
            return bool(re.search(r'\b' + re.escape(word) + r'\b', text))
        if any("一" <= c <= "鿿" for c in raw):
            return "zh"
        hokkien_phrases = ["bo lang", "bo u lang", "cai gia", "buey su", "sim buey", "kong lo"]
        hokkien_markers = ["bo", "cai", "gia", "tsai", "buey", "sioh", "lang"]
        if any(p in raw for p in hokkien_phrases) or sum(word_in(m, raw) for m in hokkien_markers) >= 2:
            return "hak"
        teochew_phrases = ["bo ing ua", "gua buee", "gua ia", "su a gu"]
        if any(p in raw for p in teochew_phrases):
            return "tdd"
        malay_markers = ["sakit", "takde", "sendiri", "penat", "rindu", "saja", "orang", "nak"]
        if sum(word_in(m, raw) for m in malay_markers) >= 1:
            return "ms"
        singlish_markers = ["lah", "leh", "lor", "liao", "sia", "hor", "meh", "wah", "aiyo", "alamak"]
        if any(word_in(m, raw) for m in singlish_markers):
            return "si"
        return "en"

    def _analyze_sentiment(self, raw: str):
        positive_words = ["happy", "good", "fine", "great", "thank", "blessing", "thanks", "joyful", "ok lah"]
        negative_words = ["sad", "lonely", "alone", "pain", "hurt", "hungry", "tired", "die", "cannot",
                          "no one", "nobody", "cry", "sakit", "bo lang", "no point"]
        pos = sum(1 for w in positive_words if w in raw)
        neg = sum(1 for w in negative_words if w in raw)
        total = pos + neg
        if total == 0:
            return SentimentLabel.NEUTRAL, 0.5
        if neg > pos:
            return SentimentLabel.NEGATIVE, round(0.5 + (neg / total) * 0.5, 2)
        if pos > neg:
            return SentimentLabel.POSITIVE, round(0.5 + (pos / total) * 0.5, 2)
        return SentimentLabel.NEUTRAL, 0.5

    def _extract_concerns(self, raw: str, request: AgnesIngestionRequest):
        concerns, details = [], []
        for category, keywords in settings.WELFARE_CONCERNS.items():
            matched = [kw for kw in keywords if kw.lower() in raw]
            if matched:
                concerns.append(ConcernCategory(category))
                details.append({"category": category, "matched_phrases": matched,
                                 "severity": "high" if len(matched) >= 2 else "medium"})
        return concerns, details

    def draft_caregiver_alert(self, senior_name: str, raw_text: str, concerns: list, flags_count: int, lang: str = "en") -> str:
        """Ask Agnes to write a personalized caregiver alert message."""
        concern_list = ", ".join(c.value.replace("_", " ") for c in concerns) if concerns else "general distress"

        if lang == "zh":
            zh_intro = "请为社区护理员写一条简短但具体的紧急通知（3-4句话）。必须直接引用长者说的具体症状和用词，不要用笼统的描述。"
            zh_name = "长者姓名："
            zh_said = "长者原话："
            zh_concerns = "检测到的问题类别："
            zh_flags = "触发了"
            zh_flags2 = "个福利警报。"
            zh_tone = "请在通知中具体提到长者说了什么症状或感受，用温和但紧迫的语气，用中文写。不要加标题或格式。"
            prompt = (
                f"{zh_intro}\n"
                f"{zh_name}{senior_name}\n"
                f"{zh_said}\"{raw_text}\"\n"
                f"{zh_concerns}{concern_list}\n"
                f"{zh_flags} {flags_count} {zh_flags2}\n"
                f"{zh_tone}"
            )
        else:
            prompt = (
                f"Write a short but specific urgent caregiver alert (3-4 sentences) for a community care worker.\n"
                f"Senior name: {senior_name}\n"
                f"Exact words they said: \"{raw_text}\"\n"
                f"Concerns detected: {concern_list}\n"
                f"{flags_count} welfare flag(s) triggered.\n"
                f"IMPORTANT: Quote the specific symptoms or feelings the senior mentioned (e.g. heart pain, not wanting to live, not eating). "
                f"Do not use vague language. Write in a warm but urgent tone. No headers or formatting."
            )

        try:
            payload = {
                "model": "agnes-2.0-flash",
                "messages": [
                    {"role": "system", "content": "You are a welfare alert assistant. Write concise, human caregiver alerts."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
            }
            response = self._http.post(f"{self._base_url}/chat/completions", json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("Agnes alert draft failed: %s", exc)
            if lang == "zh":
                zh_msg = "今天表达了"
                zh_msg2 = "的迹象，请尽快探访或致电关心。"
                return f"⚠️ {senior_name} {zh_msg}{concern_list}{zh_msg2}"
            return f"⚠️ {senior_name} has expressed signs of {concern_list} today. Please check in as soon as possible."

    def _generate_wellness_notes(self, sentiment, concerns, details):
        if sentiment == SentimentLabel.POSITIVE:
            return "Senior appears in a good mood. No immediate welfare concerns."
        concern_strs = [f"- {d['category']}: {'; '.join(d['matched_phrases'])}" for d in details]
        return f"Senior expressed {sentiment.value} sentiment ({len(concerns)} concern(s)):\n" + "\n".join(concern_strs)

    def _generate_suggested_response(self, sentiment, concerns, lang: str = "en"):
        if lang == "zh":
            if sentiment == SentimentLabel.POSITIVE:
                return "听到您这么说真好！😊 还有什么想分享的吗？"
            if ConcernCategory.FOOD_INSECURITY in concerns:
                return "我听到了，您今天还没好好吃饭。要我帮您安排社区送餐服务吗？🍜"
            if ConcernCategory.LONELINESS in concerns:
                return "您不孤单，我一直在这里陪您。要我安排义工来探访您吗？👋"
            if ConcernCategory.PHYSICAL_PAIN in concerns:
                return "很抱歉您身体不舒服。要我通知您的助理关注您的情况吗？🏥"
            if ConcernCategory.DEPRESSION_SIGNS in concerns:
                return "谢谢您告诉我您的感受。您的感受很重要，我会通知助理尽快来看您。💚"
            return "谢谢您告诉我。我已经记下来了。还有什么想说的吗？💬"
        elif lang == "ms":
            if sentiment == SentimentLabel.POSITIVE:
                return "Syukurlah mendengar itu! 😊 Ada lagi yang ingin anda kongsikan?"
            if ConcernCategory.FOOD_INSECURITY in concerns:
                return "Saya faham. Biar saya catat bahawa anda belum makan dengan betul hari ini. Mahu saya aturkan lawatan makan tengah hari komuniti? 🍜"
            if ConcernCategory.LONELINESS in concerns:
                return "Anda tidak keseorangan — saya sentiasa ada di sini untuk berbual. Mahu saya aturkan lawatan daripada sukarelawan? 👋"
            if ConcernCategory.PHYSICAL_PAIN in concerns:
                return "Saya sedih mendengar anda kesakitan. Boleh saya maklumkan kepada pembantu anda mengenai perkara ini? 🏥"
            if ConcernCategory.DEPRESSION_SIGNS in concerns:
                return "Terima kasih kerana berkongsi. Perasaan anda adalah penting. Biar saya maklumkan kepada pembantu anda supaya mereka boleh menjenguk anda tidak lama lagi. 💚"
            return "Terima kasih kerana memberitahu saya. Saya telah mencatat semuanya. Ada lagi yang ingin anda ceritakan? 💬"
        else:
            if sentiment == SentimentLabel.POSITIVE:
                return "That's wonderful to hear! 😊 Is there anything else you'd like to share?"
            if ConcernCategory.FOOD_INSECURITY in concerns:
                return "I hear you. Let me note that you haven't had proper meals. Would you like me to arrange a community lunch visit? 🍜"
            if ConcernCategory.LONELINESS in concerns:
                return "You're not alone — I'm always here to talk. Would you like me to arrange a visit from a volunteer? 👋"
            if ConcernCategory.PHYSICAL_PAIN in concerns:
                return "I'm sorry you're in pain. Should I let your helper know about this? 🏥"
            if ConcernCategory.DEPRESSION_SIGNS in concerns:
                return "Thank you for sharing. Your feelings are valid. Let me inform your helper so they can check on you soon. 💚"
            return "Thank you for telling me. I've noted everything down. Is there anything else on your mind? 💬"
