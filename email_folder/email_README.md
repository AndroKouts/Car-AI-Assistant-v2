# Outlook Email Agent

A voice-friendly, hands-free email agent built on **PydanticAI** + **Microsoft Graph API**, with full **Langfuse v4** observability. Designed as part of a multi-agent driving assistant architecture.

---

## Architecture

```
main.py                  ← REPL entry point, session management
├── observability.py     ← Langfuse v4 tracing (shared with other agents)
├── agent.py             ← PydanticAI Agent definition + tool registration
├── tools.py             ← Tool implementations (called by the LLM)
├── graph_client.py      ← Microsoft Graph REST client + MSAL auth
├── models.py            ← Pydantic data models + agent deps
└── config.py            ← Environment variable loading + validation
```

**No LangGraph** is used — the PydanticAI agent's built-in tool-call loop handles all orchestration. LangGraph would only be added if the system required explicit state-machine control flow across multiple agents.

---

## Prerequisites

- Python 3.11+
- A Microsoft 365 or Outlook.com account
- An Anthropic API key
- A Langfuse account (cloud or self-hosted)

---

## 1. Azure App Registration

You need to register an application in Azure to get Graph API access.

1. Go to [Azure Portal → App Registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps)
2. Click **New registration**
   - Name: `EmailAgent` (anything)
   - Supported account types: **Personal Microsoft accounts only** (for Outlook.com) or **Accounts in any organizational directory and personal accounts** (for both)
   - Redirect URI: leave blank for now
3. Copy the **Application (client) ID** → this is your `AZURE_CLIENT_ID`
4. Copy the **Directory (tenant) ID** → use `common` for personal accounts, or the GUID for a work tenant

### API Permissions
In your app registration → **API Permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions**, add:

| Permission | Purpose |
|---|---|
| `Mail.Read` | List and read emails |
| `Mail.ReadWrite` | Mark emails as read |
| `Mail.Send` | Send and reply to emails |
| `User.Read` | Get mailbox owner profile |
| `offline_access` | Refresh tokens (no re-login) |

Click **Grant admin consent** if required by your tenant.

### Enable Device Code Flow
In your app → **Authentication** → **Advanced settings**:
- Set **Allow public client flows** to **Yes**

---

## 2. Install Dependencies

```bash
cd email_agent
pip install -r requirements.txt
```

---

## 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your actual keys
```

Required variables:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OPENAI API key |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key |
| `LANGFUSE_BASE_URL` | Langfuse endpoint (EU or US) |
| `AZURE_CLIENT_ID` | Azure app client ID |
| `AZURE_TENANT_ID` | `common` or your tenant GUID |
| `AZURE_USER_EMAIL` | Your Outlook/M365 email address |

---

## 4. Run

```bash
python main.py
```

**First run**: The agent will print a Microsoft login URL and a short code. Open the URL in any browser, enter the code, and sign in. This is a one-time setup — tokens are cached to `.token_cache.json` and refreshed automatically.

---

## Example Commands

```
You: Show me my 5 most recent unread emails
You: Search for emails from alice@example.com
You: Read that last email from Alice
You: Reply with: Thanks, I'll get back to you tomorrow
You: Send an email to bob@example.com about the budget meeting tomorrow at 2pm
You: What folders do I have?
You: Show me emails in my Sent folder
```

---

## Observability

Every command creates a root span in Langfuse named `email-agent-command`, tagged with `email-agent` and `driving-mode`. All pydantic-ai tool calls and LLM requests are automatically nested as child spans via `Agent.instrument_all()`.

The `observability.py` module is shared with other agents in the multi-agent system — all agents feed into the same Langfuse project, grouped by `session_id`.

---

## Driving Context Design

- **Concise responses**: The system prompt instructs the LLM to keep all replies under 3–4 sentences.
- **Confirm before sending**: The agent always asks one confirmation question before sending or replying.
- **No markdown**: Output is plain text, suitable for text-to-speech if added later.
- **Error recovery**: Tool errors are reported gracefully as natural language.
- **Multi-turn memory**: Conversation history is maintained per session so the user can say "reply to that one" without re-specifying the email.

---

## Token Cache

MSAL tokens are stored at `.token_cache.json` (configurable via `MSAL_TOKEN_CACHE`). Add this file to `.gitignore`:

```
.token_cache.json
.env
```
