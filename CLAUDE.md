# CLAUDE.md

Scanrix backend: FastAPI + Motor/MongoDB service consumed by a Flutter app. How the code
works today: [ARCHITECTURE.md](ARCHITECTURE.md). API rules shared with the client:
[API_CONTRACT.md](API_CONTRACT.md). Product: [VISION.md](VISION.md). Concepts:
[LEARNING_FASTAPI.md](LEARNING_FASTAPI.md). `[judgment]` = opinion/tradeoff, not universal
best practice. **Gap** = the repo violates this today: don't copy it, and don't fix it
unasked inside an unrelated change; flag it.

## 1. Prime directive
- Production-grade only. Prefer the solid, scalable solution even if it's more work. If a
  quick patch is genuinely better (urgent, small), say so and offer the durable one as a
  follow-up.
- Before finalizing any change, check: callers (grep them), clients, data/index/migration
  impact, existing tests. Report risks explicitly.
- The Flutter app can't be force-updated: never remove, rename or retype a response field,
  change a status code or tighten validation on a live API version. Additive only.
- Ask first on architecture, schema, auth, shared conventions, anything hard to reverse.
  Decide small reversible details (names, file placement) yourself and mention them.
- Never assume business logic, API behavior, schema or validation rules. Read the code or ask.
- Non-trivial work: ask 2-5 targeted questions before coding. On "best guess", proceed and
  list assumptions.
- Never read `.env`; use `.env.example`. Never change unrelated behavior as a side effect.

## 2. Stack and structure
Python (`.python-version`), FastAPI, Motor/MongoDB (no ORM), Upstash Redis, JWT, Groq/Gemini,
Cloudinary, Docker. Target host: AWS (ECS Fargate or App Runner) [judgment, Render possible];
keep code platform-neutral, no cloud SDK imports outside `app/services`.
- **Routers** (`app/api/v1/endpoints`): parse input, `Depends`, call one service, return a
  schema. No DB access, no business rules. Gap: `scan.py` holds orchestration logic.
- **Services** (`app/services`): business logic and external integrations. New logic goes here.
- **Data access** (`app/crud`): the only place that touches Mongo. No `get_database()` elsewhere.
- **Schemas** (`app/schemas`): separate `XCreate` / `XUpdate` / `XRead` per resource. Always
  set `response_model`; never return a raw Mongo dict or leak `hashed_password`/internal fields.
- **Dependencies** via `Depends` (current user, DB, settings, rate limit). No clients built
  inside handlers; no reading `os.environ`, use `app.core.config.settings`.
- One new public resource = schemas + crud + service + router + tests, in that layering.

## 3. Size and complexity limits
- Function <= 40 lines. File <= 300 preferred, 500 hard cap. Cyclomatic complexity <= 10
  (ruff `C901`). Nesting <= 3 (use early returns/guard clauses).
- A change that crosses a limit splits the code in the same change. Existing violators
  aren't an excuse to add to them.

## 4. Performance
- No blocking calls in `async def`: sync SDKs (Groq, Gemini, Cloudinary, Upstash REST,
  `passlib`/bcrypt) go through `run_in_executor`/`asyncio.to_thread`. Gap: `check_rate_limit`
  uses the sync Redis client directly.
- No N+1: batch with `$in` / aggregation, never a query per item in a loop.
- Every list endpoint is paginated (cursor, see API_CONTRACT.md) with a max limit.
- Every index is justified by a query in a comment; every query on a large collection is
  backed by an index. Check with `explain()`.
- Timeouts on every external call (HTTP, Mongo, Redis, LLM). Retry only idempotent calls,
  with capped exponential backoff + jitter.
- Cache only with a defined key, TTL and invalidation. State the invalidation strategy in
  the PR/summary. No cache without it.
- Slow work (LLM analysis, uploads, third-party lookups) runs off the request path. Required:
  a durable queue (ARQ/Celery-style worker) for anything that must not be lost; in-process
  `BackgroundTasks` only for best-effort work. Gap: the AI analysis uses `BackgroundTasks`,
  so a restart mid-analysis leaves `verdict="analyzing"` forever. Don't extend that pattern;
  moving it to a queue is a separate, ask-first task.
- Call out time/space complexity in a comment for non-trivial algorithms; avoid O(n^2) on
  unbounded input.

## 5. Database and migrations (MongoDB)
- Schema-less is not schema-free. Enforce invariants in the DB: unique indexes (e.g. `email`,
  `barcode`), partial indexes, and `$jsonSchema` validators on new/changed collections.
- Migrations: versioned, idempotent scripts in `migrations/` (`NNNN_description.py`), run by
  the deploy pipeline, never ad hoc. Use expand -> migrate/backfill -> contract so old and new
  code both work during a rolling deploy. Never drop/rename a field in the same release that
  stops using it. Index builds must not block writes.
- Public IDs are opaque strings, never sequential. New resources use UUIDv4 `id` fields
  [judgment]; existing `ObjectId` stays until a migration is approved. Never expose raw
  `_id`/`ObjectId` shape as a contract.
- Timestamps: timezone-aware UTC `datetime` (`created_at`, `updated_at`), stored as BSON
  dates, serialized ISO 8601 with `Z`. Never store naive datetimes or local time.
- Races: prevent with unique indexes, atomic operators (`$inc`, `$set`),
  `find_one_and_update`/upserts. Never read-then-write for check-then-act. Multi-document
  transactions only if the deployment is a replica set (confirm first).
- Managed Mongo (Atlas) [judgment]. Amazon DocumentDB is Mongo-*compatible*, not Mongo:
  verify any operator/index/feature against its docs before relying on it.

## 6. Errors and validation
- Domain exceptions (`app/core/exceptions.py`) are raised in services/crud; one central
  handler maps them to RFC 9457 `application/problem+json` (`type`, `title`, `status`,
  `detail`, `instance`) plus a stable machine-readable `code` (e.g. `scan_limit_reached`).
  Codes are part of the contract: never rename. Gap: handlers raise `HTTPException(detail=...)`.
- Rolling out the problem+json body changes today's `{"detail": ...}` shape: it is a
  client-visible change, so ask first and coordinate with the Flutter app.
- Validate at the boundary with Pydantic (types, lengths, ranges, `EmailStr`, enums).
  Services trust validated input. Never validate by hand inside crud.
- No bare `except:` or `except Exception:` that swallows. Catch the specific error, log with
  context, re-raise or translate. "Fail-open" (Redis) is a documented, deliberate exception.
- Never leak stack traces, SQL/Mongo errors or secrets in responses.

## 7. Security
- Passwords: bcrypt (current) or argon2 [judgment: argon2id preferred for new work].
  Never log or return hashes.
- Auth: current scheme is a single JWT (HS256, 30 min) plus Google ID-token sign-in. Keep it;
  don't add refresh tokens, change claims or lifetimes without asking. [judgment] A rotating
  refresh token would be the durable upgrade; offer it, don't do it unasked.
- Authorization is per resource: every handler that takes an id checks the object belongs
  to `current_user` (e.g. history, scans, photos). Authentication alone isn't enough.
- Secrets only from environment (AWS Secrets Manager/SSM injected as env in prod). Never
  commit or log them; `.env.example` lists names only.
- CORS: explicit origins from settings in prod. Gap: `allow_origins=["*"]` with credentials.
- Rate limits on auth, scan and upload endpoints; 429 with `Retry-After`.
- No PII, tokens, passwords or full request bodies in logs. Gap: `print(...)` in `deps.py`.
- Dependency audit (`pip-audit`) in CI; pin versions. Validate upload type and size.

## 8. Observability and operations
- Structured JSON logs (no `print`), one request ID per request (`X-Request-ID`, generated if
  absent, echoed in the response, bound to every log line).
- `GET /health/live` (process up, no dependencies) and `GET /health/ready` (Mongo + Redis
  reachable) for the load balancer / ECS health checks. Gap: only `/` and `/health` exist.
- Graceful shutdown: handle SIGTERM, finish in-flight requests, close Mongo/HTTP clients.
  Gap: deprecated `@app.on_event`; prefer a `lifespan` context manager (ask first).
- 12-factor: config only from env via `settings`; stateless processes; logs to stdout.
- Retried unsafe operations (POST that creates/charges) accept an `Idempotency-Key`
  (API_CONTRACT.md); store the key + response with a TTL.

## 9. Banned fragile patterns
- `# type: ignore` / `# noqa` without a specific code and a reason comment.
- Hardcoded values (URLs, limits, model names, TTLs, secrets): put them in `settings`/constants.
- `sleep`-based waiting or polling inside the server; use events, queues or timeouts.
- Global mutable state (module-level caches/dicts, per-request data on globals). Shared
  clients live in `app.state`/dependencies.
- Business logic in routers; copy-paste across modules (extract a function on the 2nd use).
- Breaking changes on an existing API version (see section 1 and API_CONTRACT.md).

## 10. Testing
Gap: no test suite exists. Setting up pytest is a first-class task; ask before doing it.
- A feature isn't done without tests. Services: unit tests with fakes for external calls.
  Endpoints: integration tests via `httpx.AsyncClient` against a real MongoDB (container),
  not mocks of the DB [judgment: mongomock hides index/operator behavior].
- Always cover: auth (401/403/foreign resource), validation (422), pagination edges
  (empty, limit, last page), idempotency, rate limit.
- Bug fixes: write the failing regression test first, then fix.
- Coverage floors [judgment]: 80% overall, 90% on services and auth. A floor is a smoke
  alarm, not proof; don't write assertion-free tests to hit it.

## 11. Tooling enforced in CI
None is configured yet (Gap). Target pipeline (GitHub Actions [judgment, confirm host]),
failing the build: `ruff check` + `ruff format --check`, `mypy --strict`, `pytest` with
coverage floor, `pip-audit`, migration dry-run on a clean DB, a build of the Docker image.
Pre-commit hooks mirror the fast checks (ruff, mypy). Adding any of these = ask first;
adopt gradually (new/changed files strict, legacy allow-listed) rather than one big-bang.

## 12. Workflow rules for the AI
- Follow existing patterns. When changing an established approach, explain: what changed
  and why; the advantage; the risks; whether it's accepted best practice or a [judgment].
- Terse by default: make the change, 1-2 line summary. (Learning mode below adds teaching.)
- Run lint, types and tests when they exist. Report failures honestly with output; never
  claim a check passed that you didn't run, never skip or weaken a check to go green.
- Cloud/AWS: explain the AWS service in plain terms when it comes up (the owner is studying
  for cloud skills and knows the theory only). Don't provision or change real infra unasked.
- Keep CLAUDE.md under ~200 lines; move detail to ARCHITECTURE.md / API_CONTRACT.md.

## Learning mode (rules for the AI, every session)

The owner is an experienced Flutter/Dart dev learning FastAPI by doing real work here.
This section overrides "terse by default" **for explanations only**. Code changes stay
minimal and production-grade. Rules 1-10 apply to every bug fix, feature, change to an
existing feature, or major code change.

1. **Explain in Flutter/Dart terms.** Use the direct Dart equivalent when one exists
   (`Depends` ~ get_it / constructor injection, Pydantic ~ freezed + json_serializable,
   asyncio event loop ~ Dart's event loop). Always say where the analogy breaks down. No
   analogies from other ecosystems. No close Dart equivalent -> say so, don't force one.
2. **Concept primer before non-trivial code.** For each FastAPI/Python/DB concept the
   change uses that is new, give a short primer first. Check `LEARNING_LOG.md` and
   `LEARNING_FASTAPI.md` so you don't re-explain covered concepts.
3. **After every change, a "What you just learned" block:**
   - *Request lifecycle:* trace one request through this change (router -> dependency
     -> service/crud -> DB -> response schema), naming the files.
   - *Why this approach:* why it's production-grade, what the hobby alternative is, why
     we didn't use it.
   - *Gotchas:* the 1-3 most common beginner mistakes with this concept.
   - *Try it yourself:* one small exercise or a `curl` / `/docs` step to see the behavior.
     (No pytest suite exists yet; don't claim one does.)
4. **Bug fixes, additionally:** root cause, how to reproduce, how you found it (logs,
   debugger, query inspection, test), and how to diagnose the same class of bug alone.
5. **Scale depth to the change.** Small edit = 3-5 lines. New feature or architectural
   change = full block. Never pad.
6. **Maintain `LEARNING_LOG.md`.** After each task append: date, task, concepts covered
   (one line each), one "still to learn" item. Keep it a scannable index, not essays.
   Tick off syllabus items as they're covered and use it to suggest what to learn next.
7. **Accuracy over confidence.** If unsure about a FastAPI/Pydantic/Motor/SQLAlchemy
   behavior, say so and point to the official docs (fastapi.tiangolo.com, docs.pydantic.dev,
   motor.readthedocs.io, docs.sqlalchemy.org) instead of guessing. Never invent APIs or
   flags. Mark opinions as [judgment].
8. **Check question:** at most one short question per task, only after a meaningful
   change. Wait for the answer, correct kindly if wrong. Never a quiz session.
9. **Toggles:** the message "skip learning" = code + 1-2 line summary only, no log
   entry. "learn mode" turns it back on. The last toggle in the conversation wins.
10. **Quality bar is unchanged.** Never pick a simpler or less robust solution because it
    is easier to explain. If the right approach is complex, teach it step by step.
