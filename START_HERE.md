# KampungKonekt — Quick Start Guide

## What is this?
KampungKonekt is a web application designed to help elderly residents in Singapore stay connected and monitored for welfare concerns through voice interactions.

---

## 🖥️ How to Run the Frontend (UI)

### Option 1: Double-click (Easiest)
1. Open the folder: `C:\Users\javer\Downloads\AgnesXSMU`
2. Double-click on **`index.html`**
3. Your default browser will open with the KampungKonekt UI

### Option 2: Use the Start Menu shortcut
- Just double-click the `index.html` file and it will open in your browser

**What you'll see:**
- A large orange "Tap to Talk" button
- Quick action buttons for Schedule, Call Family, and Play Music
- Click the button to simulate voice interactions

---

## ⚙️ How to Run the Backend (AI Processing)

### Step 1: Open Command Prompt
1. Press `Windows + R` on your keyboard
2. Type `cmd` and press Enter
3. Type this command and press Enter:
   ```
   cd C:\Users\javer\Downloads\AgnesXSMU\backend
   ```

### Step 2: Run the Simulation
Type this command and press Enter:
```
python main.py --simulate
```

**OR** — Use the easy button:
1. Open the folder: `C:\Users\javer\Downloads\AgnesXSMU\backend`
2. Double-click **`run_simulation.bat`**
3. Press any key when prompted
4. Wait for the simulation to complete

### Step 3: View Results
- Open the folder: `C:\Users\javer\Downloads\AgnesXSMU\backend\reports`
- Open the file `welfare_senior_001_20260615.md` with any text editor or Word

---

## 📋 What Happens When You Run It

1. **Frontend (index.html)**: Opens the senior-friendly voice UI in your browser
2. **Backend (simulation)**: 
   - Simulates 7 days of senior interactions
   - Detects welfare concerns (loneliness, food insecurity, pain, etc.)
   - Generates a professional welfare report

---

## ❓ Troubleshooting

### "python is not recognized" error
This means Python isn't installed. Install it from: https://www.python.org/downloads/

### The browser shows a blank page
Make sure you opened `index.html` (not an empty tab). The file should contain all the KampungKonekt code.

### No welfare report generated
Check the Command Prompt/terminal for error messages. The simulation needs to run without errors.

---

## 📁 File Structure

```
AgnesXSMU/
├── START_HERE.md          ← You are here!
├── index.html             ← Frontend UI (double-click to open)
└── backend/
    ├── run_simulation.bat ← Double-click to run simulation
    ├── main.py            ← Main backend script
    ├── requirements.txt   ← Python dependencies
    ├── .env               ← Configuration (API keys)
    ├── config/            ← Settings
    ├── models/            ← Data models
    ├── api/               ← Agnes API integration
    ├── memory/            ← Memory storage (SQLite)
    ├── analytics/         ← Anomaly detection
    ├── reports/           ← Generated welfare reports
    └── data/              ← Local database