# Car Driving Assistant — Architecture

A hands-free voice assistant for the car. Speak naturally; the assistant
controls your email (Microsoft 365) and Spotify through specialised
sub-agents while you keep your eyes on the road.

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

## File structure

```
project/
├── .env                         Your secrets — never commit this
├── .env.example                 Template showing all required variables
├── docker-compose.yml           Postgres service (run with docker compose up -d)
├── alembic.ini                  Alembic configuration
│
├── main.py                      Entry point — wires deps, starts bridge
├── realtime_bridge.py           WebSocket loop + audio I/O + sub-agent dispatch
├── config.py                    All configuration — single source of truth
├── observability.py             Langfuse OTel setup
│
├── email_agent.py               PydanticAI email agent (gpt-4.1-mini)
├── graph_client.py              Async MS Graph API client (MSAL auth + token refresh)
├── models.py                    Pydantic models + EmailAgentDeps dataclass
├── tools.py                     Email tool implementations
│
├── spotify_agent.py             PydanticAI Spotify agent (gpt-4.1-mini)
├── spotify_client.py            Spotify API wrapper (Spotipy OAuth + token refresh)
│
├── db/
│   ├── models.py                SQLAlchemy ORM table definitions
│   ├── database.py              Async engine, session factory, init_db()
│   └── service.py               DatabaseService — all read/write operations
│
├── alembic/
│   ├── env.py                   Async-aware migration environment
│   └── versions/
│       └── 0001_initial.py      First migration — creates all tables
│
└── requirements.txt
```

No `orchestration/` directory, no LangGraph. The bridge IS the orchestrator.

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
runs on the host as normal (audio hardware requires host access). All drive
history is persisted to a named Docker volume so data survives container
restarts.

### Tables

| Table             | What it stores                                          |
|-------------------|---------------------------------------------------------|
| `sessions`        | One row per drive — start time, end time, user          |
| `turns`           | One row per request — transcript, intent, result, timing|
| `email_actions`   | Email-specific detail — action type, subject, sender    |
| `spotify_actions` | Spotify-specific detail — action type, track, artist    |
| `preferences`     | Per-user settings — priority senders, voice, model      |

DB writes are fire-and-forget (`asyncio.create_task`) so they never block
the audio stream or delay the spoken response.

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
source. Use the pre-built wheel from `pipwin` instead:

```bash
pip install pipwin
pipwin install pyaudio
```

Alternatively download the matching wheel from
https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio and install with:
```bash
pip install PyAudio-0.2.14-cpXX-cpXX-win_amd64.whl
```
Replace `cpXX` with your Python version (e.g. `cp311` for Python 3.11).
pyaudio works fine on Windows once installed — only the install step differs.

### 2. Install Docker

Download and install Docker Desktop from https://www.docker.com/products/docker-desktop.
On Linux, install Docker Engine and the Docker Compose plugin via your package manager.

### 3. Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment variables

Copy `.env.example` to `.env` and fill in your values. `config.py` loads
this automatically on startup and raises a clear error for any missing
required value.

```bash
# OpenAI (Realtime API access required)
OPENAI_API_KEY=sk-...

# Microsoft 365 / Azure — from your Azure app registration
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_USER_EMAIL=you@yourcompany.com
AZURE_TENANT_ID=common                          # optional, default: common

# Spotify — from your Spotify Developer Dashboard
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback   # must match dashboard

# Postgres — matches docker-compose.yml defaults
POSTGRES_USER=assistant
POSTGRES_PASSWORD=assistant
POSTGRES_DB=car_assistant
POSTGRES_HOST=localhost                         # optional, default: localhost
POSTGRES_PORT=5432                              # optional, default: 5432

# Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com    # optional
```

**First-run authentication (one time only)**

Email: MSAL prints a URL and short code in the terminal. Open the URL in a
browser, enter the code, and sign in with your Microsoft 365 account. The
token is cached to `.token_cache.json`; all future runs refresh silently.

Spotify: Spotipy opens a browser tab for OAuth consent. After approving, the
token is cached to `.spotify_cache`; all future runs refresh silently.

### 5. Start Postgres

```bash
docker compose up -d
```

Postgres is now running on `localhost:5432`. Data is persisted to a named
Docker volume and survives container restarts.

### 6. Run the database migration

```bash
alembic upgrade head
```

This creates all five tables. Only needed on first run and after any future
schema changes.

### 7. Run the assistant

```bash
python main.py
```

Speak to the assistant. Press Ctrl+C to end the session.

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
2. Add one tool entry to `_REALTIME_TOOLS` in `realtime_bridge.py`:
   `handle_navigation_request(instruction)`
3. Add a `_run_navigation_agent()` method to `RealtimeBridge`
4. Add a `case "handle_navigation_request"` branch in `_handle_tool_call()`
5. Add a `create_navigation_action()` method to `db/service.py`
6. Add a `navigation_actions` table to `db/models.py` and a new migration

Six small, isolated changes. Nothing else needs to touch.
