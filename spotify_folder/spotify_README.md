# 🎵 Spotify AI Agent

A natural-language Spotify controller built with **Pydantic AI**, **Langfuse** observability, and the **Spotify Web API**.  
Type commands in plain English — the agent understands intent and executes the right Spotify action.


---

## Architecture

```
User input (text)
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│                   Pydantic AI Agent                     │
│  Model: openai:gpt-4o-mini                              │
│                                                         │
│  Tools:                                                 │
│    skip_song        previous_song    play_track         │
│    pause_playback   resume_playback  get_now_playing    │
│    set_volume       toggle_shuffle   add_to_queue       │
│    list_devices                                         │
└────────────────────┬────────────────────────────────────┘
                     │ tool calls
                     ▼
            ┌─────────────────┐
            │  SpotifyClient  │  (spotipy + Spotify Web API)
            └─────────────────┘

Observability:
  ① Logfire → Langfuse OTLP   low-level spans: LLM requests, tool calls, retries
  ② Langfuse Python SDK        high-level traces: one Trace per user command, grouped by session
```

---

## Prerequisites

| Requirement | Where to get it |
|------------|----------------|
| Python 3.11+ | python.org |
| OpenAI API key | platform.openai.com |
| Spotify Developer App | developer.spotify.com/dashboard |
| Langfuse account | cloud.langfuse.com (free tier available) |
| Spotify Premium | Required for playback control via API |

---

## Quick Start

### 1 — Clone & install

```bash
git clone <this-repo>
cd spotify-agent

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2 — Create a Spotify Developer App

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Click **Create App**
3. Fill in any name/description
4. Set **Redirect URI** to "http://127.0.0.1:8888/callback"
5. Copy the **Client ID** and **Client Secret**

### 3 — Get Langfuse keys

1. Sign up at [cloud.langfuse.com](https://cloud.langfuse.com) (or self-host)
2. Create a new project
3. Go to **Settings → API Keys**
4. Copy the **Public Key** and **Secret Key**

### 4 — Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=sk-...

SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI="http://127.0.0.1:8888/callback"

LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 5 — Run

```bash
python main.py
```

**First run only:** Spotipy will open your browser for Spotify OAuth.  
After authorising, the token is cached in `.spotify_cache` — you won't need to authenticate again.

---

## Example Commands

```
You: skip
🎵  Skipped to next track.

You: play Bohemian Rhapsody
🎵  Now playing: "Bohemian Rhapsody" by Queen.

You: play some good feel songs from the 2000s
🎵  Playing playlist: "2000s Feel Good Hits".

You: what's playing?
🎵  ▶ Playing: "Hey Ya!" by Outkast (from Speakerboxxx/The Love Below).

You: volume 40
🎵  Volume set to 40%.

You: shuffle on
🎵  Shuffle enabled 🔀.

You: add Mr. Brightside to the queue
🎵  Added to queue: "Mr. Brightside" by The Killers.

You: pause
🎵  Playback paused.

You: something chill for the drive home
🎵  Playing playlist: "Chill Vibes".

You: quit
Goodbye! 🎵
```

---

## Observability in Langfuse

After running a few commands, open your Langfuse project to see:

### Traces view
Each command is a **named Trace** (`spotify-command`) grouped by `session_id`.  
You can filter by tag (`spotify`, `music-assistant`) and see input/output at a glance.

### Spans (via Pydantic AI OTel)
Drill into any trace to see low-level spans:
- `pydantic_ai.agent.run` — the full agent invocation
- `pydantic_ai.model.request` — the actual OpenAI API call (with token counts)
- `pydantic_ai.tool.*` — each tool call with arguments and result
- Retry spans if the model needed to recover from an error

---

## Project Structure

```
spotify-agent/
├── main.py            # CLI entry point & conversation loop
├── agent.py           # Pydantic AI agent + all tool definitions
├── spotify_client.py  # Spotify Web API wrapper (spotipy)
├── observability.py   # Langfuse v4 observability (OTel + session tracing)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Design Decisions

### Why `gpt-4o-mini`?
Speed matters for a driving assistant. `gpt-4o-mini` handles intent classification and Spotify search query construction reliably at lower latency and cost than `gpt-4o`.

### Why rolling message history?
Each agent run passes the last `MAX_HISTORY_MESSAGES` (default 20) messages as context. This lets the model handle follow-ups like *"lower it a bit more"* or *"play that again"*, while keeping the prompt size bounded.

### Why no LangGraph?
LangGraph adds value for multi-agent coordination, branching workflows, and persistent checkpointing. None of those are needed here — a single Pydantic AI agent with tool-calling is simpler, faster, and easier to maintain for this use case.

---

## Extending the Agent

Add a new Spotify capability in three steps:

1. **Add a method** to `SpotifyClient` in `spotify_client.py`
2. **Register a tool** in `agent.py` using the `@agent.tool` decorator
3. **Update the system prompt** table in `agent.py` so the model knows when to use it

No other files need to change.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `No active Spotify device found` | Open the Spotify app on any device and start playing something |
| `Premium required` | Spotify's API requires Premium for playback control |
| `INVALID_CLIENT` | Double-check `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `.env` |
| OAuth loop on every run | Delete `.spotify_cache` and re-authenticate |
| Langfuse traces not showing | Check `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` and ensure the host is reachable |
