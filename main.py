"""
main.py
───────
Entry point for the car driving assistant.

Startup sequence
────────────────
1. Import config — triggers load_dotenv() and validates all required env vars.
2. Initialise Langfuse observability and instrument all PydanticAI agents.
3. Open a GraphClient session (MSAL handles auth + token refresh internally).
4. Instantiate SpotifyClient (Spotipy handles OAuth + token refresh internally).
5. Run the RealtimeBridge for the duration of the drive session.

Authentication — first run only
────────────────────────────────
Email:   MSAL prints a URL + code in the terminal. Open the URL in a browser,
         enter the code, sign in with your Microsoft 365 account. Token is
         cached to disk (.token_cache.json by default); all future runs
         refresh silently with no user action needed.

Spotify: Spotipy opens a browser tab for OAuth consent. After approving,
         token is cached to .spotify_cache; all future runs refresh silently.

Environment variables  (set in .env or shell)
─────────────────────────────────────────────
OPENAI_API_KEY          Required
AZURE_CLIENT_ID         Required  (from your Azure app registration)
AZURE_USER_EMAIL        Required  (your Microsoft 365 email address)
AZURE_TENANT_ID         Optional  (default: "common")
SPOTIFY_CLIENT_ID       Required
SPOTIFY_CLIENT_SECRET   Required
SPOTIFY_REDIRECT_URI    Optional  (default: http://127.0.0.1:8888/callback)
LANGFUSE_PUBLIC_KEY     Required
LANGFUSE_SECRET_KEY     Required
LANGFUSE_BASE_URL       Optional  (default: https://cloud.langfuse.com)

Usage
─────
    python main.py

Press Ctrl+C to end the drive session.
"""

from __future__ import annotations

import asyncio
import logging
import sys

# ── config must be imported first — calls load_dotenv() and validates env vars
import shared.config as config  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("main")


async def main() -> None:

    # ── Observability ─────────────────────────────────────────────────────────
    # Must happen before any agent modules are imported so that
    # Agent.instrument_all() catches the module-level agent singletons.
    from shared.observability import setup_observability
    observer = setup_observability()
    logger.info("Observability ready (Langfuse)")

    # ── Spotify ───────────────────────────────────────────────────────────────
    # SpotifyClient reads SPOTIFY_* env vars itself (already loaded by config)
    # and manages its own OAuth cache — nothing else needed here.
    spotify_deps = None
    try:
        from spotify_folder.spotify_client import SpotifyClient
        from spotify_folder.spotify_agent import SpotifyDeps
        spotify_deps = SpotifyDeps(spotify=SpotifyClient())
        logger.info("Spotify ready")
    except ImportError as exc:
        logger.warning("Spotify unavailable: %s", exc)
    except Exception as exc:
        logger.warning("Spotify setup failed: %s", exc)

    # ── Email + bridge (share one GraphClient for the whole session) ──────────
    # GraphClient is an async context manager — opening it triggers MSAL auth
    # (silent refresh if cached, device-code prompt on first run).
    # We keep it open for the entire drive session so all email tool calls
    # share one authenticated HTTP connection with automatic token refresh.
    # user_email comes from config — no need to call get_me() at startup.
    from db.database import init_db
    from db.service import DatabaseService
    from email_folder.graph_client import GraphClient
    from email_folder.models import EmailAgentDeps
    from orchestration.realtime_bridge import RealtimeBridge

    await init_db()
    db = DatabaseService()
    logger.info("Database ready")

    async with GraphClient() as graph_client:
        email_deps = EmailAgentDeps(
            graph_client=graph_client,
            user_email=config.AZURE_USER_EMAIL,
            driving_mode=True,
        )
        logger.info("Email ready  user=%s", config.AZURE_USER_EMAIL)

        bridge = RealtimeBridge(
            observer=observer,
            email_deps=email_deps,
            spotify_deps=spotify_deps,
            db=db,
        )

        logger.info("Car assistant starting — speak to begin")
        logger.info("Press Ctrl+C to end the session\n")

        try:
            await bridge.run()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")

    observer.shutdown()
    logger.info("Session ended. Goodbye.")


if __name__ == "__main__":
    asyncio.run(main())
