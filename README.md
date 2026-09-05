# Kisan Dost 🌾 ("Farmer's Friend")

An AI agronomy assistant for Pakistani farmers, built for the Agentic AI
Hackathon using the **OpenAI Agents SDK**, running on **Google Gemini**
(free tier, via Gemini's OpenAI-compatible endpoint — no OpenAI credits
needed).

Two ways to use it:
- **Terminal version** (`main.py`) — the core hackathon requirement
- **Web version** (`app.py` + `static/` folder) — a bonus browser-based chat
  UI that reuses the exact same agent code
- **Flask backend** (`app_flask.py`) — an alternative backend, useful as a
  fallback if FastAPI/uvicorn has issues in your environment

---

## Features

**7 domain tools across 4 specialist agents:**

| Specialist Agent | Tools it uses |
|---|---|
| Agronomy Agent | Crop Advisor, Fertilizer Calculator, Irrigation & Weather Advisor |
| Pest Doctor Agent | Pest & Disease Doctor (with safety guardrail) |
| Market Agent | Mandi Price Lookup, Govt Support Finder |
| Finance Agent | Profit Estimator |

A **Triage Agent** reads the farmer's question and hands off to the right
specialist.

**Safety features:**
- Input guardrail — rejects questions unrelated to farming, while still
  allowing greetings, name introductions, and intake answers (district,
  land size, season, water) through, since these are a normal part of the
  conversation flow, not off-topic requests.
- Output guardrail — blocks unsafe pesticide dosages and human-medical
  advice.
- Strict language matching — replies in English, Roman Urdu, or Urdu
  script based ONLY on the farmer's most recent message, never defaulting
  to Roman Urdu just because the topic is Pakistani agriculture.

**Intake flow:** before answering, the Triage Agent checks whether it
already knows the farmer's **name, district, land size (acres), season
(Rabi/Kharif), and water availability**, stored in a `FarmerProfile` object
passed as run context. If any of that is missing, it asks for it in one
warm message instead of answering right away. As soon as any detail is
given, it's saved immediately via a tool call (`update_farmer_profile`, with
an `update_profile` alias registered too — see Known Issues below for why).
Once given, it stops asking and uses those details to tailor every later
answer. Urgent questions (e.g. a pest emergency) are handled immediately,
intake or not.

---

## Project file structure

```
kisan_dost/
├── main.py            # all agent logic: FarmerProfile, tools, agents, guardrails, intake rule, terminal loop
├── app.py             # web backend (FastAPI) — imports and reuses main.py
├── app_flask.py        # alternative web backend (Flask) — same agent logic, simpler dev server
├── static/
│   ├── index.html     # chat page layout + name-gate overlay
│   ├── style.css       # soil/wheat/field agriculture theme, pinstripe accent
│   └── script.js        # chat logic, markdown rendering, name gate, farm-panel autofill
├── requirements.txt    # Python dependencies
├── .env                # your real Gemini API key (NEVER share/commit this)
├── .env.example         # safe template for .env (this one IS fine to share)
├── .gitignore            # keeps .env, venv/, and the session file out of GitHub
└── README.md              # this file
```

---

## Setup

1. Clone the repo and open it in your editor.
2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```
3. Activate it:
   ```powershell
   venv\Scripts\activate
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Copy `.env.example` → `.env` and paste your own Gemini API key (get one
   free at https://aistudio.google.com/apikey):
   ```
   GEMINI_API_KEY=your-real-key-here
   GEMINI_MODEL=gemini-flash-lite-latest
   ```

---

## How to run

**Terminal version (core requirement):**
```powershell
venv\Scripts\activate
python main.py
```
Type `exit` or `quit` to stop.

**Web version (FastAPI):**
```powershell
venv\Scripts\activate
uvicorn app:app --reload
```
Then open `http://127.0.0.1:8000` in your browser. Press `Ctrl+C` to stop.

**Web version (Flask alternative):**
```powershell
venv\Scripts\activate
pip install flask
python app_flask.py
```
Then open `http://127.0.0.1:8000`. Also exposes a quick diagnostic at
`http://127.0.0.1:8000/api/health` to check the server and Gemini are both
reachable without needing to use the chat UI first.

---

## Known issues & fixes applied

| Problem | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'dotenv'` | Wrong Python interpreter (not venv) | Activate venv before running |
| `.env.example` / `.gitignore` lost their leading dot | File save stripped it | Rename in VS Code (right-click → Rename) |
| `Unknown name "verbosity"` from Gemini | Agents SDK sends an OpenAI-only field Gemini rejects | `ModelSettings(verbosity=None)` on every agent |
| `404 — model no longer available` | Google retired the pinned model version | Use `gemini-flash-lite-latest` (auto-tracks Google's current model) |
| `429 — RateLimitError` | Free tier limit; each turn uses multiple AI calls | Wait ~30–60s between messages; the Flask backend surfaces this clearly instead of hanging |
| Urdu script showed broken in terminal | Terminals can't render joined Arabic-script text | Use the web frontend instead |
| Bot replies showed literal `**` / `1.` markers | Frontend displayed raw markdown as plain text | Added a markdown-lite renderer in `script.js` |
| `ImportError: cannot import name 'FarmerProfile'` | `app.py` expected a `FarmerProfile` context class that didn't exist yet in `main.py` | Added `FarmerProfile` dataclass + `update_farmer_profile` tool in `main.py` |
| Web UI hung/spun forever on send | No timeout around the Gemini call; a locked/corrupted `SQLiteSession` file from an earlier crash | Wrapped the call in `asyncio.wait_for(..., timeout=45)`, added catch-all exception handling, deleted the stale session file |
| Intake asked for name again after it was already given | Input guardrail rejected greetings/name introductions as "off-topic" before the Triage Agent could save them | Taught the topic-guardrail agent to explicitly allow greetings, name intros, and intake answers through |
| `[Server error: ModelBehaviorError] Tool update_farmer_profile not found in agent Topic Guardrail Checker` | `SQLiteSession` history (including prior tool calls) was being forwarded into the tool-less guardrail-checker agent | Guardrail now extracts only the farmer's latest plain text before checking topic relevance |
| `[Server error: ModelBehaviorError] Tool update_profile not found in agent Triage Agent` | Gemini occasionally hallucinates a shortened tool name (`update_profile` instead of `update_farmer_profile`) | Registered `update_profile` as a second tool, aliasing the same underlying logic, so either name works |
| Replies defaulted to Roman Urdu even when the farmer wrote in English | Language instruction was descriptive, not strict, and the Pakistani-farming framing biased the model toward Roman Urdu | Rewrote the language rule to strictly check only the farmer's most recent message and forbid defaulting to Roman Urdu |
| Name-gate only asked once per browser (via `localStorage`) | By design — intended as a one-time onboarding step | Changed `script.js` so the name overlay shows on every page load/refresh instead of being skipped |

---

## Limitations

- No database: the web app keeps conversation state only in memory (plus a
  local SQLite session file for chat history). A server restart clears the
  in-memory `FarmerProfile`, and the agent will ask for district/land/
  season/water again next run.
- Single shared farmer profile per server process in the FastAPI/Flask
  backends — fine for a local demo, not for multiple concurrent real users.
  A production version would need per-user auth and persistent storage.
- Gemini's free tier has request-per-minute and per-day limits; heavy
  testing can trigger `429` errors — space out requests if this happens.

---

## Before you submit / present

- [ ] Test all 7 tools live (crop advisor, pest doctor, fertilizer calc,
      mandi price, irrigation/weather, profit estimator, govt schemes)
- [ ] Test the input guardrail (ask something off-topic, like a coding
      question) — confirm it's rejected but greetings/intake answers are not
- [ ] Test the output guardrail (ask a pest question and check the
      dosage/safety note)
- [ ] Test the full intake flow: refresh the web app, enter a name, answer
      the district/land/season/water question, confirm the sidebar fills in
- [ ] Test language matching: send one message in English, one in Roman
      Urdu, and (if possible) one in Urdu script — confirm each reply
      matches the language you just used
- [ ] Test that a bot reply with a numbered/bulleted list renders properly
      (no literal `**` or `1.` showing)
- [ ] Test the mobile drawer (narrow the browser window, confirm the
      sidebar collapses into the "Your farm & quick prompts" toggle)
- [ ] Double-check `.env` is NOT committed to GitHub (confirm it's not in
      the file list shown by GitHub Desktop before committing)
- [ ] Push to GitHub with GitHub Desktop, verifying `.env` and `venv/` do
      not appear in the published repo