# Voice AI Patient Registration System

A phone-based AI agent that conversationally registers new patients, saves
them to a persistent Postgres database, and exposes the data through a REST
API + a small web dashboard.

Built entirely on free tiers: **Vapi** (AI voice assistant platform), **Groq**
(free, extremely fast LLM inference), **Neon** (free serverless Postgres),
and **Vercel** (free hosting for both backend and frontend).

> This project was built with AI assistance, which the assessment's
> own FAQ explicitly allows. Make sure you can walk through and explain every
> part of it before your review call — that's what's actually being graded.

---

## 1. Architecture

Caller (phone/web) --> Vapi (STT + TTS & Voice Orchestration) --> FastAPI webhook
|
v
Groq LLM (conversation NLU)
|
v
Python validators.py (re-checks
every value before trusting it)
|
v
PostgreSQL (Neon) <--> REST API
|
v
Static dashboard (Vercel)

**Why this stack, specifically:**

- **Vapi** for voice handling, STT, and TTS instead of managing manual media-streaming WebSockets or rigid IVRs. Vapi handles the real-time audio pipeline smoothly and forwards events via webhooks.
- **Groq** for the LLM: free API tier, and importantly *fast* — a phone call
  needs a sub-few-second response or the caller sits in silence.
- **FastAPI**: handles webhook events per conversation turn; all state lives in Postgres (`call_sessions` table), so it survives serverless cold starts and even a server restart.
- **Neon Postgres**: free tier, serverless-friendly connection pooling —
  works well from Vercel's short-lived functions.
- **Vercel**: hosts the FastAPI backend as a Python serverless function
  (`api/index.py`) and the dashboard as a static site — both free.

### Separation of concerns (backend/app/)

| File | Responsibility |
|---|---|
| `routers/voice.py` | Webhook endpoints only — processes voice assistant events, no business logic |
| `conversation.py` | The state machine: merges LLM output with validated data, decides what happens next |
| `groq_service.py` | Talks to Groq, owns the system prompt, returns structured JSON |
| `validators.py` | Deterministic, code-level validation for every field (never trust the LLM alone) |
| `crud.py` / `models.py` / `schemas.py` | Database layer |
| `routers/patients.py` | Public REST API |

---

## 2. Prompt engineering notes

The full system prompt lives in `backend/app/groq_service.py`. Key decisions:

- The model's **only** job is natural-language understanding (extract fields,
  decide the next line, detect language/corrections/restart intent). It
  never touches the database and every extracted value is re-validated in
  Python (`validators.py`) before being trusted — satisfies the spec's
  "do not rely solely on the voice agent for validation."
- **Strict JSON output** (`response_format={"type": "json_object"}`) so the
  backend can parse it reliably instead of regexing free text.
- On every turn we re-send "already collected fields" + "still missing
  required fields" explicitly, instead of trusting the model to remember
  state across a long call — this avoids drift over a multi-turn call.
- A five-state stage machine (`collecting` → `offering_optional` →
  `confirming` → `complete`, plus `restart`) keeps the read-back/confirmation
  requirement enforced structurally, not just hoped for.

---

## 3. Local setup

### 3.1 Python version

You have Python 3.13 and 3.11 installed. **Use 3.13** — it's what's pinned in
`backend/.python-version`, and Vercel's Python runtime officially supports
3.13 (and 3.14), so your local venv and the deployed environment match
exactly. All dependencies here (FastAPI, SQLAlchemy, psycopg2-binary,
groq) have current wheels for 3.13.

```bash
cd backend
python3.13 -m venv venv

# activate it
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows

pip install --upgrade pip
pip install -r requirements.txt
3.2 Get your free accounts + keys
Groq (LLM) — https://console.groq.com → sign up free → "API Keys" →
create a key. This is your GROQ_API_KEY.

Neon (Postgres) — https://neon.tech → sign up free → create a
project → copy the pooled connection string (toggle "Pooled
connection" on the dashboard) → this is your DATABASE_URL.

Vapi (Voice AI Assistant) — https://dashboard.vapi.ai → create an assistant and configure your webhook URL.