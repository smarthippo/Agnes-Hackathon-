<img width="718" height="1236" alt="image" src="https://github.com/user-attachments/assets/4e0a670d-ff70-4ae1-b21c-905b9bbf6285" />
<img width="831" height="1273" alt="image" src="https://github.com/user-attachments/assets/6675d655-fa20-4a7d-b222-bef90592e131" />

# KampungKonekt Backend

Singapore's hyper-local welfare monitoring system for isolated elderly residents.

## Architecture

```
KampungKonekt Backend
├── config/          # Settings, environment variables, welfare keywords
├── models/          # Pydantic data schemas
├── api/             # Agnes Text API client with dialect fallback
├── memory/          # SQLite time-series storage
├── analytics/       # Anomaly detection engine
├── reports/         # Markdown welfare report generator
├── main.py          # Orchestrator & CLI entry point
└── .env             # API keys & configuration
```

## Quick Start

### 1. Install Dependencies

From the repo root:

```bash
pip install -r backend/requirements.txt
```

### 2. Configure Environment

Edit `backend/.env` with your Agnes API key:

```env
AGNES_API_KEY=your_real_api_key_here
SENIOR_ID=senior_001
SENIOR_NAME=Grandma Lim
```

### 3. Start the Server

From the repo root:

```bash
python backend/server.py
```

The app will be live at **http://localhost:8000**

The server auto-reloads when you save any backend file — no restart needed.

### 4. Run the Demo (optional)

```bash
# Simulate a week of declining interactions
cd backend
python main.py --simulate

# Process a single voice input
python main.py --process "Bo lang cai gia"

# Run welfare check
python main.py --check senior_001

# Generate report
python main.py --report senior_001
```

## Dialect Support

The system handles these languages/dialects out of the box:

| Language | Code | Example Phrase | Translation |
|----------|------|----------------|-------------|
| English | `en` | "Nobody cooks for me" | Direct |
| Singlish | `si` | "Send li sia" | So lonely |
| Malay | `ms` | "sakit hati" | Heartache |
| Mandarin | `zh` | "我很孤独" | I am very lonely |
| Hokkien | `hak` | "bo lang cai gia" | Nobody cooks for me |
| Teochew | `tdd` | "bo ing ua a" | Nobody's around |

## Welfare Detection Rules

| Rule | Threshold | Severity |
|------|-----------|----------|
| 3+ consecutive negative days | Configurable | Yellow → Red |
| 2+ food concerns in 7 days | 2 mentions | Yellow |
| 3+ loneliness mentions in 7 days | 3 mentions | Yellow |
| Any physical pain mention | 1 mention | Yellow |
| Any depression indicator | 1 mention | Red |
| 3+ days silence (active senior) | 3 days | Green (Monitor) |

## Output

Reports are saved to `backend/reports/welfare_<senior_id>_<date>.md`

Example report structure:
```markdown
# Welfare Report — KampungKonekt
**Report Generated:** 2026-06-15 10:30 SGT
**Senior Name:** Grandma Lim

> 🔴 **HIGH RISK — Immediate attention required**

## Summary Statistics
| Metric | Value |
|--------|-------|
| Total Interactions | 7 |
| Negative Sentiment | 4 |

## Recommended Actions
1. 🔴 **URGENT:** Schedule immediate welfare check visit within 24 hours.
2. 🍜 Arrange community meal delivery
3. 👋 Assign SMU Student Volunteer
```

## Production Deployment

For production, uncomment the FastAPI/Uvicorn dependencies and run:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```
<img width="1024" height="1536" alt="image" src="https://github.com/user-attachments/assets/24b1fe15-5601-4af7-ba4a-8157ebfcf031" />

