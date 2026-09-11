# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Scanrix backend: a FastAPI service for a "health product scanner" that a Flutter app
consumes. Given a barcode (or OCR'd ingredient text) it returns an ingredient-level
safety analysis. Fully async (Motor for MongoDB, `asyncio` throughout).

Product vision, problem statement, and target users: see [VISION.md](VISION.md).

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install groq google-genai        # see "Missing dependencies" below

# Run the dev server (requires a populated .env — see Configuration)
uvicorn app.main:app --reload        # http://127.0.0.1:8000, docs at /docs

# List Gemini models visible to your API key (ad-hoc script, not a test suite)
python test_models.py
```

There is no lint, formatter, or test framework configured. `test_models.py` is a
standalone diagnostic script, not pytest. The "tested all end points" commit refers to
manual testing via `/docs`.

## Configuration

`app/core/config.py` loads settings from `.env` via pydantic-settings (`case_sensitive`).
Required (no default — app won't start without them): `MONGODB_URL`, `SECRET_KEY`,
`GEMINI_API_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`.
`GROQ_API_KEY` has a placeholder default; the AI service treats the literal
`"your-groq-api-key-here"` as "unset" and skips straight to Gemini.

## Architecture

Layered, no ORM/ODM:

- `app/api/v1/endpoints/*` — route handlers, grouped under `/api/v1/{auth,products,scan,history}`.
- `app/crud/*` — the only place that touches MongoDB. Collections are referenced by bare
  string name via `get_database()`: `users`, `products`, `scan_history`.
- `app/services/*` — external integrations (Open Food Facts, Open Beauty Facts, AI).
- `app/models/*` — **not** data models; each file is a `*_helper(doc)` function that
  converts a raw Mongo document (with `ObjectId`) into a JSON-safe dict. Documents are
  plain dicts with no enforced schema.
- `app/schemas/*` — Pydantic request/response models.
- `app/core/*` — config, JWT/password (`security.py`), custom `HTTPException` subclasses
  (`exceptions.py`).

### Auth

JWT bearer, HS256 (`python-jose` + `passlib`/bcrypt). `app/api/deps.py::get_current_user`
decodes the token, loads the user by email (`sub` claim), and returns the **raw Mongo
user dict** (handlers index it as `current_user["_id"]`, not attribute access).

### Redis (Upstash REST client, sync)

Two uses, both fail-open on Redis errors:
1. `deps.check_rate_limit` — per-user daily scan cap of 10, key
   `rate_limit:scans:{user_id}:{YYYY-MM-DD}`, 24h TTL. Applied to both `/scan` endpoints.
2. `ai_service` — 30-day cache of AI analyses, key = md5 of `{category}:{sorted,normalized
   ingredients}`, so identical ingredient lists never re-hit the LLM.

### Scan flow (`app/api/v1/endpoints/scan.py`) — the core of the app

`POST /api/v1/scan/` with a barcode:
1. Look up `products` by barcode. Hit → write `scan_history`, return.
2. Miss → `asyncio.gather` races Open Food Facts and Open Beauty Facts; first valid dict wins.
3. Found externally → persist the product immediately with `verdict="analyzing"`,
   return right away, and schedule `run_ai_analysis_background` as a FastAPI
   `BackgroundTask`. That task later updates the same document with score/verdict/ingredients.
   **The Flutter client polls `GET /api/v1/products/{barcode}` until `verdict` flips off
   `"analyzing"`** (`"error"` / `"unknown"` are terminal too).
4. Found nowhere → 404.

`POST /api/v1/scan/analyze-text` is the OCR path: skips the DB and external APIs, calls
the AI synchronously, returns the analysis inline (nothing persisted).

### AI analysis waterfall (`app/services/ai_service.py`)

Redis cache → **Groq** (`llama-3.1-8b-instant`) → **Gemini** (`gemini-2.5-flash`) →
static keyword-heuristic fallback (`_get_fallback_analysis`, always succeeds). Every LLM
call is a sync SDK call pushed through `run_in_executor`. The prompt demands a fixed JSON
shape; `_parse_json_response` strips markdown fences and validates required keys. Result
(including the fallback) is cached.

## Gotchas

- **Missing dependencies:** `ai_service.py` imports `groq`, and both it and
  `test_models.py` do `from google import genai` (the `google-genai` client SDK).
  Neither `groq` nor `google-genai` is in `requirements.txt` — `requirements.txt` pins
  the older `google-generativeai` instead. Install both manually.
- Token lifetime: `create_access_token` defaults to 15 min when called with no
  `expires_delta`, but `/auth/login` passes `ACCESS_TOKEN_EXPIRE_MINUTES` (30).
- Startup/shutdown use the deprecated `@app.on_event` hooks (fine on FastAPI 0.133).
- CORS is `allow_origins=["*"]` with credentials — intentional for dev, noted as
  needing a real domain in prod.
- Auth endpoints wrap every DB call in `asyncio.wait_for(...)` with per-call timeouts and
  translate failures to the custom exceptions in `core/exceptions.py`; other endpoints
  don't do this.
- `product_helper` requires `barcode`, `name`, `brand`, `category` keys to exist (raw
  `[...]` access) — external-service parsers must always populate them.
