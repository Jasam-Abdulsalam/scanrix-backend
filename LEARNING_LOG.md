# Learning Log

Running syllabus and index for learning FastAPI by working in this repo. Newest entries at
the bottom of "Log". Concepts are one-liners; deeper explanations live in
`LEARNING_FASTAPI.md`. The AI uses this to avoid repeating explanations and to suggest
what to learn next.

## Syllabus (suggested order; tick when covered)

Stack note: this repo uses MongoDB via Motor, not SQL. Items 11-12 apply if/when the repo
moves to Postgres; the Mongo equivalents are in 9-10.

- [ ] 1. Python for Dart devs: types/hints, `dict` vs class, `None`, comprehensions, venv/pip
- [x] 2. How a FastAPI app boots: ASGI, uvicorn, `FastAPI()`, routers, `include_router`
- [x] 3. Path/query/body params and automatic `/docs` (OpenAPI)
- [ ] 4. Pydantic v2 schemas: validation, Create/Update/Read split, `response_model`
- [x] 5. `async`/`await` and the event loop: `async def` vs `def`, blocking calls, `run_in_executor`
- [x] 6. Dependency injection: `Depends`, sub-dependencies, `get_current_user`
- [ ] 7. Errors: `HTTPException`, custom exceptions, exception handlers, status codes
- [ ] 8. Config and secrets: pydantic-settings, `.env`, 12-factor
- [ ] 9. MongoDB with Motor: collections, queries, `ObjectId`, indexes, projections
- [ ] 10. Pagination, sorting and avoiding N+1 / unbounded queries
- [ ] 11. (Postgres path) SQLAlchemy sessions, transactions, ORM vs Core
- [ ] 12. (Postgres path) Alembic migrations, zero-downtime-safe changes
- [ ] 13. Auth: password hashing, JWT, refresh tokens, per-resource authorization
- [ ] 14. Third-party sign-in: Google ID-token verification flow
- [ ] 15. Background work: `BackgroundTasks` vs a durable job queue, polling, idempotency
- [ ] 16. External calls: `httpx`, timeouts, retries, caching (Redis), fail-open vs fail-closed
- [ ] 17. Middleware, CORS, rate limiting
- [ ] 18. Testing: pytest, `TestClient`/`httpx.AsyncClient`, dependency overrides, regression tests
- [ ] 19. Logging, request IDs, health/readiness probes, graceful shutdown
- [ ] 20. Tooling and deploy: ruff, mypy, CI, Docker

## Foundations track (the 9 skills for directing AI to build production systems)

Studied alongside the syllabus above; each lesson tags which foundation it builds.
Numbers in brackets point to syllabus items.

- [ ] F1. How the web works: HTTP methods, status codes, headers, JSON, cookies vs bearer [2, 3]
- [ ] F2. Reading Python fluently: what a function does, where data comes from, failure paths [1, 5]
- [ ] F3. Data and databases: modeling, indexes, slow queries, unique constraints, races [9, 10]
- [ ] F4. Security: hashing vs encryption, JWT, authn vs authz, secrets, CORS [13, 14, 17]
- [ ] F5. Failure thinking: timeouts, retries, restarts mid-request, third-party outages [15, 16]
- [ ] F6. Testing and verifying: what a good test checks, running things yourself [18]
- [ ] F7. Git, deployment, operations: diffs, env vars, Docker, logs, health checks, AWS [19, 20]
- [ ] F8. System design basics: app/API/DB/cache/queue, stating requirements clearly [15, 16]
- [ ] F9. Reviewing AI like an engineer: small tasks, ask for tradeoffs, "what could break?"

## Log

<!-- Append per task:
### YYYY-MM-DD: <task>
- Concepts: <one line each>
- Still to learn: <one item>
-->

### 2026-10-09: Lesson 1a, toy router (`playground/toy_router.py`)
- Concepts: route = decorated function stored in a (method, path) -> function dict
- Concepts: decorator runs at startup; the function runs once per request
- Concepts: uvicorn (server) vs FastAPI (app), ASGI as the interface between them
- Concepts: include_router prefixes are string-joined at startup (`/api/v1` + `/history` + `/`)
- Still to learn: real FastAPI task 1 (path/query params, 422 validation errors, `/docs`)

### 2026-10-09: Lesson 1b, real FastAPI (`playground/lesson1.py`)
- Concepts: path param (`/items/{item_id}`) vs query param (`?verbose=true`) from the function signature
- Concepts: type hints drive validation (bad value -> 422 before the function runs); `/docs` generated from code
- Still to learn: Pydantic models for JSON request bodies (lesson 2)

### 2026-10-09: Lesson 2, Pydantic (`playground/lesson2.py`) - partly done
- Concepts: BaseModel (fields -> constructor + validation + JSON conversion); Field(min_length); EmailStr
- Concepts: 422 error shape (`type`, `loc`, `msg`, `input`); `input` echoes the body, including passwords
- Still to learn: cases b/c of the task and "why not return the password" (response models, lesson 5)

### 2026-10-09: Lesson 3, async and the event loop (`playground/lesson3.py`)
- Concepts: event loop, `await` frees the loop while waiting; blocking call in `async def` freezes all requests (measured: /fast 4.09s vs 0.009s)
- Concepts: plain `def` endpoints run in a thread pool, so blocking there doesn't freeze the loop
- Concepts: calling `async def` returns a coroutine, nothing runs until awaited (differs from Dart)
- Still to learn: `run_in_executor` / `asyncio.to_thread` for blocking SDKs; Motor's async API (lesson 6)

### 2026-10-09: Lesson 4a, Depends toy (`playground/toy_depends.py`)
- Concepts: dependency = function that runs before the handler; if it raises, the handler never runs
- Concepts: one reusable check instead of repeating it in every handler
- Concepts: async HTTP with `httpx.AsyncClient`, `async with`, `timeout`
- Still to learn: real `Depends` with headers (`lesson4.py`), 401 vs 403, dependency chains

### 2026-10-09: Lesson 4b, real Depends (`playground/lesson4.py`)
- Concepts: `Depends(fn)` in a signature, `Header(default=None)` fills a param from an HTTP header
- Concepts: 401 (not authenticated) raised from a dependency; dependency chain (`get_admin` -> `get_current_user`)
- Still to learn: 401 vs 403 in depth, custom exceptions and a central error handler (lesson 5)

### 2026-10-12: Bug fix, Prop 65 seed header detection (`scripts/seed_prop65.py`)
- Concepts: substring match vs exact match for parsing structured text; "stateful" iterators (`csv.reader` is consumed as you loop, so `any(...)` over it advances it)
- Concepts: upsert helpers create side-effect docs (canonical + CAS aliases), so deleting an ingredient also means deleting its aliases
- Concepts: `ObjectId` in one collection vs the same id stored as a plain string in another (`aliases.ingredient_id`)
- Still to learn: pytest basics and fixtures (no pytest installed in venv yet)

### 2026-10-12: Bug fix, fuzzy matching false positives (`ingredient_matcher.py`, `ingredient_db_service.py`)
- Concepts: fuzzy scorers (`WRatio` rewards substrings, `ratio` compares whole strings); a "match" needs a confidence policy (accept / suggest / reject)
- Concepts: in-process end-to-end test with `TestClient` + `app.dependency_overrides` (swap `Depends` like a fake in get_it); VPN/IP allowlist affects DB connections
- Still to learn: tuning thresholds with a golden product set (plan Phase 6)

### 2026-10-13: Versioned data, informational facts, recompute-on-read (`seed_off.py`, `rule_engine.py`, `ingredient_db_service.py`)
- Concepts: stale derived data (stored verdict vs fresh evaluation); recompute-on-read vs cache vs versioned snapshot; docker image rebuild vs restart (code is baked into the image)
- Concepts: seed data as "recognition" vs "hazard" facts; inheriting values through a parent hierarchy at seed time
- Still to learn: versioned snapshot (option 3) and Redis cache invalidation

### 2026-10-14: Unknown-ingredient scan counter (`crud_unknown_ingredient.py`, `scripts/top_unknowns.py`)
- Concepts: atomic upsert with `$inc` / `$setOnInsert` (no read-then-write race); `bulk_write(ordered=False)` = one round trip for many names
- Concepts: `BackgroundTasks` for best-effort work that must never fail the request; whitelisting client-supplied values (category) before they become DB keys
- Still to learn: durable queue (ARQ/Celery-style) for work that must not be lost

### 2026-10-14: EU cosmetic inventory seed (`scripts/seed_eu_inventory.py`)
- Concepts: file encodings (Windows-1252 vs UTF-8 decode error); a shared identifier (CAS) must not be assigned to one of several names; recognition data vs hazard data
- Still to learn: how to review seeded data quality (spot-check sample rows) before trusting it

### 2026-10-14: Parser bullets and "Contains:" declarations, allergen gaps (`ingredient_parser.py`, `seed_off.py`)
- Concepts: regex lookbehind/lookahead to tell "Contains: milk" apart from "(contains milk)" and "contains less than 2% of"; whitelist vocabulary instead of trusting free text
- Concepts: separating data from code (`data/curated/allergen_links.json` merged into the seed)
- Still to learn: always check a script has a dry-run before running it (an undeclared run of a seed script writes to the DB in `.env`)

### 2026-10-14: India FSSAI permitted-additive list (`extract_fssai.py`, `seed_fssai.py`)
- Concepts: one-time offline extraction (dev-only dependency) producing a small JSON that the seed reads, so Docker needs no PDF library
- Concepts: positive-only data (a listed item is true, a missing item is "unknown", never "banned"); measuring extraction recall against a known list before trusting it
- Still to learn: validating extracted data against the source document row by row

### 2026-10-14: Opt-in "Analyze with AI" endpoint (`ai_explain_service.py`, `deps.check_ai_rate_limit`)
- Concepts: fail-closed vs fail-open rate limiting (cost-bearing endpoint refuses when Redis is down); `asyncio.to_thread` + `wait_for` to bound a blocking SDK call
- Concepts: treating LLM output as untrusted input (validate with Pydantic, drop instead of repair); keeping AI data out of the trusted safety tables
- Still to learn: a durable job queue for slow AI work (API_CONTRACT section 9) instead of a blocking request
