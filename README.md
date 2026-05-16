# Car Driving Assistant — Architecture

A hands-free voice assistant for the car. Speak naturally; the assistant
controls your email (Microsoft 365) and Spotify through specialised
sub-agents while you keep your eyes on the road. A React dashboard lets
you review drive history, track activity, and configure the assistant
from your browser.

---

## Data flow

```
Driver speaks
     │  PCM16 audio, 24 kHz
     ▼
┌──────────────────────────────────────────────────────────────┐
│         OpenAI Realtime API  (gpt-realtime-2)                │
│                                                              │
│  • Listens with semantic VAD (auto turn detection)           │
│  • Transcribes speech                                        │
│  • Detects intent: email OR spotify                          │
│  • Calls ONE of two registered tool functions:               │
│      handle_email_request(instruction: str)                  │
│      handle_spotify_request(instruction: str)                │
│  • Speaks the tool result back to the driver                 │
│                                                              │
│  Does NOT do any email or Spotify work itself.               │
└────────────────────────┬─────────────────────────────────────┘
                         │  response.function_call_arguments.done
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                RealtimeBridge._handle_tool_call()            │
│                                                              │
│   match tool_name:                                           │
│     "handle_email_request"    →  _run_email_agent()          │
│     "handle_spotify_request"  →  _run_spotify_agent()        │
│     _                         →  fallback string             │
│                                                              │
│   Each runner:                                               │
│     1. Opens a Langfuse child span                           │
│     2. Calls PydanticAI sub-agent .run(instruction, deps)    │
│     3. Returns plain-text result string                      │
│     4. Persists turn + action to Postgres (fire-and-forget)  │
└────────────────────────┬─────────────────────────────────────┘
                         │  plain-text string
                         ▼
        conversation.item.create (function_call_output)
             +  response.create
                         │
                         ▼
           Realtime model speaks the answer to the driver
```

---

## System overview

```
Browser (localhost:5173 dev / localhost:8000 prod)
     │
     │  HTTP / REST
     ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI  (server.py)                      │
│                                                             │
│  GET  /api/sessions              session history            │
│  GET  /api/sessions/{id}/turns   turn detail                │
│  GET  /api/sessions/{id}/spotify spotify actions            │
│  GET  /api/sessions/{id}/email   email actions              │
│  GET  /api/preferences           load settings              │
│  PUT  /api/preferences           save settings              │
│  POST /api/assistant/start       start bridge task          │
│  POST /api/assistant/stop        stop bridge task           │
│  GET  /api/assistant/status      is assistant running?      │
│  WS   /ws/live                   real-time event stream     │
└──────────────┬──────────────────────────┬───────────────────┘
               │                          │
               ▼                          ▼
        PostgreSQL DB             RealtimeBridge
        (Docker)                  (asyncio.Task)
```

---

## File structure

```
project/
├── .env                         Your secrets — never commit this
├── .env.example                 Template showing all required variables
├── docker-compose.yml           Postgres service
├── alembic.ini                  Alembic configuration
│
├── server.py                    FastAPI entry point — replaces main.py
├── realtime_bridge.py           WebSocket loop + audio I/O + sub-agent dispatch
├── config.py                    All configuration — single source of truth
├── observability.py             Langfuse OTel setup
│
├── api/
│   ├── __init__.py
│   └── routes/
│       ├── __init__.py
│       ├── sessions.py          Session + turn + action endpoints
│       ├── preferences.py       GET + PUT preferences
│       ├── assistant.py         Start / stop / status
│       └── live.py              WebSocket /ws/live — real-time events
│
├── email_agent.py               PydanticAI email agent (gpt-4.1-mini)
├── graph_client.py              Async MS Graph API client (MSAL auth)
├── models.py                    Pydantic models + EmailAgentDeps
├── tools.py                     Email tool implementations
│
├── spotify_agent.py             PydanticAI Spotify agent (gpt-4.1-mini)
├── spotify_client.py            Spotify API wrapper (Spotipy OAuth)
│
├── db/
│   ├── models.py                SQLAlchemy ORM table definitions
│   ├── database.py              Async engine, session factory, init_db()
│   └── service.py               DatabaseService — all read/write operations
│
├── alembic/
│   ├── env.py                   Async-aware migration environment
│   └── versions/
│       ├── 0001_initial.py      Creates all tables
│       └── 0002_preferences_update.py  Adds new preference columns
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx             React entry point
│       ├── App.jsx              Router + persistent header
│       ├── api.js               All API calls in one place
│       ├── index.css            Global styles + orb animations
│       ├── hooks/
│       │   └── useWebSocket.js  WebSocket hook with auto-reconnect
│       ├── pages/
│       │   └── LivePage.jsx     Live session view
│       └── components/
│           ├── AssistantControls.jsx   Start/Stop button + status indicator
│           ├── AssistantVisualiser.jsx Orb + transcript feed + action card
│           ├── SessionList.jsx         Drive history list
│           ├── SessionDetail.jsx       Session drill-down with tabs
│           └── PreferencesPanel.jsx    Settings form
│
└── requirements.txt
```

No `orchestration/` directory, no LangGraph. The bridge IS the orchestrator.
The assistant runs as an `asyncio.Task` inside the FastAPI process, controlled
from the browser.

---

## Cost design

| Layer          | Model          | Role                                  | Cost      |
|----------------|----------------|---------------------------------------|-----------|
| Realtime model | gpt-realtime-2 | Speech I/O, intent routing only       | Expensive |
| Email agent    | gpt-4.1-mini   | All email reasoning + tool calls      | Cheap     |
| Spotify agent  | gpt-4.1-mini   | All Spotify reasoning + tool calls    | Cheap     |

Model is set once in `config.SUB_AGENT_MODEL` — change it there to upgrade
both agents at once.

The Realtime model stays cheap because it never reads emails or queries
Spotify. Its only job is to listen, classify intent, package the instruction
in a short string, and speak back the result.

---

## Database (Postgres + Docker)

Postgres runs in a Docker container — no manual installation needed. The app
runs on the host (audio hardware requires host access). All drive history is
persisted to a named Docker volume so data survives container restarts.

### Tables

| Table             | What it stores                                          |
|-------------------|---------------------------------------------------------|
| `sessions`        | One row per drive — start time, end time, user          |
| `turns`           | One row per request — transcript, intent, result, timing|
| `email_actions`   | Email-specific detail — action type, subject, sender    |
| `spotify_actions` | Spotify-specific detail — action type, track, artist    |
| `preferences`     | Per-user settings — senders, voice, volume, model       |

DB writes are fire-and-forget (`asyncio.create_task`) so they never block
the audio stream or delay the spoken response.

---

## Dashboard (React + FastAPI)

The dashboard runs at `localhost:8000` (production) or `localhost:5173`
(development). It has three screens:

**Live view** — dedicated page showing the assistant in real time:
- Animated orb that changes colour and pulse speed based on state
  (idle → listening → thinking → speaking)
- Live transcript feed showing driver speech and assistant responses
  as chat bubbles, streaming word by word as the assistant speaks
- Action card that appears when a tool completes, showing what the
  assistant just did (e.g. "Playing Bohemian Rhapsody by Queen")
- All driven by a persistent WebSocket connection to the server

**Session list** — all drive sessions, date, duration, request count,
live/completed status. Click any row to drill in.

**Session detail** — three tabs:
- All Requests — full turn log with transcript, intent, instruction, result, timing
- Spotify — every track played, skipped, or queued with artist
- Email — every email read, replied to, or sent

**Preferences** — settings form that writes directly to the database:
- Microsoft account email
- Priority and blocked senders (tag input)
- Default Spotify volume (slider)
- Startup playlist / mood
- Preferred Spotify device
- Assistant voice (dropdown)
- Sub-agent model (dropdown)
- Driving mode toggle

The **Start Session / Stop Session** button lives in the header on every page.
Clicking Start launches the bridge as a background task; clicking Stop cancels
it and finalises the session record in the database.

---

## Observability (Langfuse)

```
realtime-session  [root span — entire drive session]
├── email-agent-call         [one span per email request]
│   ├── list_emails          [PydanticAI tool span — automatic]
│   └── read_email           [PydanticAI tool span — automatic]
└── spotify-agent-call       [one span per Spotify request]
    └── skip_song            [PydanticAI tool span — automatic]
```

All spans share the same `session_id` and appear grouped in Langfuse.
PydanticAI internal spans are emitted automatically via `Agent.instrument_all()`.

---

## Setup

### 1. System dependencies (audio)

**macOS**
```bash
brew install portaudio
```

**Ubuntu / Debian**
```bash
sudo apt-get install portaudio19-dev python3-dev
```

**Windows**

`pip install pyaudio` fails on Windows because it tries to compile from
source. Use `pipwin` instead:
```bash
pip install pipwin
pipwin install pyaudio
```
pyaudio works fine on Windows once installed — only the install step differs.

### 2. Install Docker Desktop

Download from https://www.docker.com/products/docker-desktop and install it.
Open Docker Desktop and wait for the engine to show as running before
continuing. On Linux, install Docker Engine and the Compose plugin via your
package manager instead.

### 3. Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Frontend dependencies (first time only)

```bash
cd frontend && npm install && cd ..
```

### 5. Environment variables

Copy `.env.example` to `.env` and fill in your values.

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Microsoft 365 / Azure
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_USER_EMAIL=you@outlook.com
AZURE_TENANT_ID=common                              # optional

# Spotify
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback

# Postgres
POSTGRES_USER=assistant
POSTGRES_PASSWORD=assistant
POSTGRES_DB=car_assistant

# Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

**First-run authentication (one time only)**

Email: MSAL prints a URL and short code in the terminal. Open the URL,
enter the code, sign in. Token cached to `.token_cache.json` — silent
refresh from then on.

Spotify: Spotipy opens a browser tab for OAuth consent. Token cached to
`.spotify_cache` — silent refresh from then on.

### 6. Start Postgres

```bash
docker compose up -d
```

Postgres runs on `localhost:5432`. The container restarts automatically
when Docker Desktop starts — you never need to run this again unless you
manually stopped it.

### 7. Run the database migrations

```bash
alembic upgrade head
```

Creates all five tables. Only needed on first run and after schema changes.

### 8. Run the server

```bash
uvicorn server:app --reload --port 8000
```

### 9. Run the frontend (development)

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173`. Click **Start Session** to begin a drive.

---

## Production (single command)

Build the frontend once:
```bash
cd frontend && npm run build && cd ..
```

Then only run FastAPI:
```bash
uvicorn server:app --port 8000
```

Open `http://localhost:8000`. Everything — dashboard and API — is served
from one URL. No separate Vite server needed.

---

## Day to day usage

1. Open Docker Desktop — wait for engine to show running
2. Run `uvicorn server:app --port 8000`
3. Open `http://localhost:8000`
4. Click **Start Session** — speak to the assistant
5. Click **Stop Session** when done
6. Review the drive in the session history

---

## Example interactions

| Driver says                          | What happens                                        |
|--------------------------------------|-----------------------------------------------------|
| "Do I have any unread emails?"       | email_agent → list_emails → spoken count + senders  |
| "Read me the last email from Sarah"  | email_agent → search + read_email → spoken body     |
| "Reply to Bob, say I'll be 10 late"  | email_agent → confirm → reply_to_email              |
| "Skip this song"                     | spotify_agent → skip_song → "Skipped."              |
| "Play some 90s rock"                 | spotify_agent → play_track → "Playing…"             |
| "Volume to 70"                       | spotify_agent → set_volume → "Volume set to 70."    |
| "What's playing?"                    | spotify_agent → get_now_playing → spoken track info |

---

## Adding a third capability (e.g. navigation)

1. Build a new PydanticAI agent: `navigation_agent.py`
2. Add one tool to `_REALTIME_TOOLS` in `realtime_bridge.py`
3. Add `_run_navigation_agent()` to `RealtimeBridge`
4. Add a `case` branch in `_handle_tool_call()`
5. Add `create_navigation_action()` to `db/service.py`
6. Add a `navigation_actions` table to `db/models.py` + new migration
7. Add API endpoints in `api/routes/sessions.py`
8. Add a tab in `SessionDetail.jsx`

Eight small, isolated changes. Nothing else needs to touch.