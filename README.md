# KampungKonekt

Singapore's AI companion and welfare monitoring system for elderly residents.

A voice-first web app that lets seniors speak naturally in English, Mandarin, or Malay — detecting welfare concerns in real time and alerting caregivers when needed, while talking back in a warm human voice.

<img width="718" height="1236" alt="KampungKonekt main screen" src="https://github.com/user-attachments/assets/4e0a670d-ff70-4ae1-b21c-905b9bbf6285" />

---

## Features

- **Voice input** — tap the mic, speak naturally in English, Mandarin, or Malay
- **AI companion** — Gemini 2.5 Flash generates warm, personalised responses
- **Voice output** — the app speaks back using browser TTS (Google voices)
- **Personalised memory** — AI remembers the last 5 conversations per user and references them naturally
- **Respectful addressing** — addresses seniors as Uncle/Auntie, 伯伯/阿姨, or Pakcik/Makcik based on gender and language
- **User profiles** — name, gender, health conditions, family contact, preferred language — all stored per user
- **Welfare detection** — keyword-based analysis flags loneliness, pain, food insecurity, depression
- **Caregiver alerts** — red-risk interactions trigger automatic WhatsApp alerts to family
- **Language switcher** — switch language at any time from any screen
- **Welfare reports** — Markdown reports generated per senior

---

## Architecture

```
Agnes-Hackathon/
├── index.html            # Single-page frontend (voice UI, TTS, Gemini AI)
├── config.js             # Frontend secrets — gitignored, not committed
├── config.example.js     # Template for config.js
├── backend/
│   ├── server.py         # FastAPI server (process, users, reports)
│   ├── config/           # Settings and environment variables
│   ├── models/           # Pydantic data schemas
│   ├── api/              # Agnes Text API client
│   ├── memory/           # SQLite time-series storage
│   ├── analytics/        # Anomaly detection engine
│   ├── reports/          # Markdown welfare report generator
│   └── .env              # Backend API keys — gitignored
```

---

## Quick Start

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd Agnes-Hackathon
pip install -r backend/requirements.txt
```

### 2. Configure backend environment

Create `backend/.env`:

```env
AGNES_API_KEY=your_agnes_api_key_here
AGNES_API_BASE_URL=https://api.agnes.ai
GEMINI_API_KEY=your_gemini_api_key_here
SENIOR_ID=senior_001
SENIOR_NAME=Grandma Lim
```

### 3. Configure frontend API key

Copy `config.example.js` to `config.js` and fill in your Gemini key:

```js
const FRONTEND_CONFIG = {
    GEMINI_API_KEY: 'your_gemini_api_key_here',
};
```

> `config.js` is gitignored and will never be committed. Get a free key at [aistudio.google.com](https://aistudio.google.com) — or ask the team lead for the shared key.

### 4. Start the server

```bash
python backend/server.py
```

The app will be live at **http://localhost:8000**

---

## Languages Supported

| Language | Voice |
|----------|-------|
| English | Google UK English Female |
| Mandarin (中文) | Google 普通话（中国大陆） |
| Malay (Bahasa Melayu) | Google Bahasa Indonesia |

Dialect input (Singlish, Hokkien, Teochew, etc.) is understood by the backend keyword engine.

---

## Personalisation & Memory

Each user has their own profile and conversation history stored in SQLite, scoped by their unique user ID.

| Profile Field | Description |
|---|---|
| Name | Used to address the senior directly |
| Gender | Determines honorific (Uncle/Auntie, 伯伯/阿姨, Pakcik/Makcik) |
| Health conditions | e.g. "Diabetic, knee pain" — included in every AI prompt |
| Preferred language | Saved on login, used for voice and AI response language |
| Family contact | WhatsApp number for caregiver alerts |

The AI is given the senior's profile and their last 5 conversations on every interaction, so it can say things like *"Uncle Ahmad, you mentioned your knee was hurting yesterday — how is it feeling today?"*

---

## Welfare Detection

| Concern | Trigger | Alert Level |
|---------|---------|-------------|
| Loneliness | 3+ mentions in 7 days | Yellow |
| Food insecurity | 2+ mentions in 7 days | Yellow |
| Physical pain | Any mention | Yellow |
| Depression signs | Any mention | Red |
| 3+ consecutive negative days | — | Red |

Red alerts trigger a WhatsApp notification to the senior's linked family contact.

---

## Welfare Reports

Auto-generated Markdown reports are saved to `backend/reports/welfare_<senior_id>_<date>.md`.

---

## Security Notes

- `config.js` (Gemini frontend key) — gitignored, never committed
- `backend/.env` (Agnes + Gemini backend keys) — gitignored, never committed
- See `config.example.js` and `backend/.env.example` for templates
