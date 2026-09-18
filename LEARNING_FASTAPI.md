# Learning FastAPI, through this codebase

This is a plain-English reference for the FastAPI concepts used in this repo,
taught through a real change: the profile-completion feature
(`GET /auth/me`, `PATCH /auth/me`, `profile_completed` flag). Read it next to
the actual files — `app/api/v1/endpoints/auth.py`, `app/schemas/user.py`,
`app/crud/crud_user.py`, `app/api/deps.py`.

If you know Flutter/Dart, several of these concepts map almost 1:1 — noted
where relevant.

---

## 1. The request path: how a URL becomes a function call

```
app/main.py
  → includes app/api/v1/api.py (api_router)
    → includes app/api/v1/endpoints/auth.py (router, prefix "/auth")
      → @router.get("/me")   → function get_me()
      → @router.patch("/me") → function update_me()
```

This is just URL → function mapping, the same idea as `go_router` mapping a
path string to a screen widget. `@router.get(...)` / `@router.post(...)` /
`@router.patch(...)` are **decorators** — Python's version of an annotation
that wraps a function with extra behavior (here: "expose this as an HTTP
endpoint"). You don't need to understand decorators deeply to use FastAPI;
just know `@router.<method>("/path")` = "this function handles that
method+path."

**Industry-standard HTTP methods**, and what each *should* mean (this is a
convention almost every REST API follows, not FastAPI-specific):

| Method | Meaning | Example in this repo |
|---|---|---|
| `GET` | Read, no side effects, safe to call repeatedly | `GET /auth/me` — fetch my profile |
| `POST` | Create something new | `POST /auth/register` — create a user |
| `PATCH` | Partially update existing data (send only changed fields) | `PATCH /auth/me` — update name/photo |
| `PUT` | *Replace* the entire resource (not used in this repo) | — |
| `DELETE` | Remove something | — |

We used `PATCH` (not `PUT`) for profile updates because the frontend only
ever sends `{name, photo_url}` — a partial shape — not the entire user
document. That's the deciding rule: **PATCH = partial payload, PUT = full
replacement payload.**

---

## 2. Pydantic schemas: validation as a data class

```python
class UserProfileUpdate(BaseModel):
    name: str = Field(..., min_length=1)
    photo_url: Optional[str] = None
```

This is a **Pydantic model** — think of it like a Dart class with validation
built into its constructor. When a request body arrives as raw JSON,
FastAPI:
1. Parses it against this class.
2. If `name` is missing or empty, it auto-rejects the request with a `422
   Unprocessable Entity` **before your function body runs** — you never
   write `if not name: raise ValueError(...)` by hand.
3. If it's valid, you get a real Python object (`payload.name`,
   `payload.photo_url`) with autocomplete, not a loose dict.

This is the same value proposition as a `freezed`/`json_serializable` data
class in Dart with custom validators — the shape and rules live in one
place, and invalid data never reaches your business logic.

**`Optional[str] = None`** means "this field can be absent or `null`" —
directly equivalent to Dart's `String?` with a default.

---

## 3. Two schemas per concept: request shape vs response shape

Notice there are *two* different classes involved in one feature:
- `UserProfileUpdate` — what the frontend **sends** (request body)
- `UserResponse` — what the backend **sends back** (response body)

This is deliberate, not duplication. The request shape and response shape
are usually different: a request to *update* a profile only needs
`name`/`photo_url`; the response describing "here's the full user" needs
`id`, `email`, `created_at`, etc. Keeping separate classes for "what comes
in" vs "what goes out" is a FastAPI/Pydantic convention you'll see in almost
every real API — don't try to reuse one class for both.

---

## 4. `response_model=`: an enforced filter, not just documentation

```python
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return user_helper(current_user)
```

`user_helper()` returns a Python **dict** that includes `hashed_password`
(look at `app/models/users.py` — it's right there). But the response the
frontend actually receives never contains it, because `response_model=
UserResponse` filters the dict through the `UserResponse` schema before
serializing to JSON — and `UserResponse` simply doesn't declare a
`hashed_password` field, so it gets silently dropped.

**This is the single most important FastAPI concept to internalize:**
`response_model` isn't a docs annotation — it's an active filter/validator
on every response. It's how sensitive fields (passwords, internal flags)
stay out of API responses even when your internal dict/document has them.

---

## 5. Dependency Injection: `Depends(...)`

```python
async def get_me(current_user: dict = Depends(get_current_user)):
```

`Depends(get_current_user)` tells FastAPI: "before running this function,
call `get_current_user` and pass its return value in as `current_user`."
`get_current_user` (in `app/api/deps.py`) does the actual work: reads the
`Authorization: Bearer <token>` header, decodes the JWT, looks the user up
in MongoDB, and returns the user dict — or raises a 401 if any of that
fails.

Every protected endpoint just declares `current_user: dict =
Depends(get_current_user)` as a parameter and gets a verified, logged-in
user handed to it — no endpoint re-implements "check the token" itself.

If you've used **Riverpod**: this is the same shape as
`ref.watch(currentUserProvider)` — you declare what you need, the framework
resolves and injects it, and the resolution logic lives in exactly one
place.

`Depends()` can also depend on other `Depends()` — see
`check_rate_limit(current_user: dict = Depends(get_current_user))` in
`deps.py`: the rate limiter depends on "logged in user," which itself
depends on "valid token." FastAPI resolves the whole chain automatically.

---

## 6. Async/await and why every endpoint here is `async def`

```python
async def update_me(payload: UserProfileUpdate, current_user: dict = Depends(get_current_user)):
    updated_user = await asyncio.wait_for(update_user_profile(...), timeout=10.0)
```

This is the exact same `async`/`await` keywords and mental model as Dart —
if you've written `Future<T>` code in Flutter, you already understand this.
`await` pauses this request's execution at the database call without
blocking the whole server; other requests keep being served on the same
process in the meantime. This project deliberately uses an async MongoDB
driver (`motor`, not the sync `pymongo`) end-to-end so nothing blocks.

`asyncio.wait_for(coro, timeout=10.0)` is a **timeout wrapper**: it races
the actual work against a countdown, and raises `asyncio.TimeoutError` if
the DB call takes longer than 10 seconds. This repo's convention (see every
`auth.py` endpoint) is: wrap external calls (DB, third-party APIs) in
`wait_for`, catch the timeout, and convert it into a proper HTTP error — so
a slow database never just hangs a request indefinitely.

---

## 7. Custom exception classes = consistent error responses

```python
class NotFoundException(HTTPException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
```

(`app/core/exceptions.py`) Instead of writing `raise HTTPException(status_code=404, detail="...")`
everywhere, this repo defines named exception classes per HTTP status
code. `raise NotFoundException(detail="User not found")` is more readable at
the call site, and guarantees every 404 in the app has the same shape. This
is a very common pattern in production APIs — you'll see it called
"exception hierarchies" or "domain exceptions" in other frameworks too.

**Common status codes and what they mean** (used throughout this repo):

| Code | Name | When |
|---|---|---|
| `200` | OK | Successful GET/PATCH |
| `201` | Created | Successful POST that creates something (`/register`) |
| `401` | Unauthorized | Missing/invalid/expired auth token |
| `404` | Not Found | Resource doesn't exist |
| `409` | Conflict | Trying to create something that already exists (`/register` with a taken email) |
| `422` | Unprocessable Entity | Request body failed Pydantic validation (automatic, you don't raise this yourself) |
| `429` | Too Many Requests | Rate limit hit (`check_rate_limit`) |
| `500` | Internal Server Error | Unexpected bug |
| `504` | Gateway Timeout | A downstream call (DB, LLM) took too long |

---

## 8. MongoDB here has no ORM — just dicts, and why `user_helper()` exists

Most backend tutorials use an ORM (Django's ORM, SQLAlchemy) that maps
database rows to Python objects automatically. This project doesn't use one
— MongoDB documents are just plain Python `dict`s, with no schema
enforcement at the database level (see `CLAUDE.md`'s Architecture section).

This means **conversion has to happen manually**. MongoDB's `_id` field is a
special `ObjectId` type, not a JSON-serializable string — so
`user_helper()` (`app/models/users.py`) exists purely to turn a raw Mongo
document into a plain JSON-safe dict:

```python
"id": str(user["_id"]),   # ObjectId → string
```

Every endpoint that returns a user goes through `user_helper()` first. If
you forget this step and try to return a raw Mongo document directly,
FastAPI will error trying to serialize the `ObjectId`.

---

## 9. JWT auth flow, end to end

1. `POST /auth/login` verifies email+password, then calls
   `create_access_token(data={"sub": user["email"]}, ...)` — this creates a
   signed token (JWT) encoding the user's email and an expiry time. It's
   returned to the frontend as `access_token`.
2. The frontend stores this token (e.g. secure storage in Flutter) and
   sends it on every future request as `Authorization: Bearer <token>`.
3. `get_current_user` (`deps.py`) decodes and verifies the token's
   signature+expiry, pulls the email back out (`payload.get("sub")`), and
   looks up that user fresh from MongoDB on **every single request** — the
   token itself doesn't carry the user's current data, just their identity.

This is why `profile_completed` had to become a **database field**, not
something baked into the token — the token is only reissued at login, so a
token-only flag couldn't reflect changes made later (exactly the problem
statement you gave me for this task).

---

## 10. Why this feature shape (`/me` + a completion flag) is an industry pattern

The `GET /auth/me` endpoint returning "whoever the token says you are" is
an extremely common convention — GitHub, Stripe, Slack, and Twitter/X's
APIs all expose a `/me` or `/user` endpoint with exactly this shape: "no
need to pass an ID, just tell me about the authenticated caller." It's the
natural pattern any time a client needs to answer "who is currently logged
in, and what's their state?" on app startup.

The **persisted "is onboarding complete" flag** you asked for is also a
standard pattern — you'll recognize it from:
- LinkedIn prompting "complete your profile" on every login until you do.
- Slack's post-signup workspace setup flow.
- Instagram/Twitter nudging new accounts to add a profile photo.

All of these work the same way under the hood: a boolean (or an enum with
more granular steps) stored on the user record, checked once at app
startup via a `/me`-style call, used purely to decide which screen to show
first — never stored client-side as the source of truth, because (as you
identified) a client-only flag can't survive reinstalls, new devices, or
multiple logins.

---

## 11. Quick glossary

| Term | Plain English |
|---|---|
| **Path operation** | FastAPI's name for "a function decorated with `@router.get/post/...`" |
| **Pydantic model** | A validated data class for request/response shapes — like a Dart class with built-in validation |
| **`response_model`** | The schema FastAPI filters your return value through before sending JSON |
| **Dependency (`Depends`)** | A reusable piece of setup logic (auth, rate limiting) FastAPI runs and injects before your endpoint body |
| **`async`/`await`** | Same as Dart — pause this request without blocking the server |
| **Serialization** | Converting a Python object/dict into JSON (and back) |
| **ASGI** | The async server protocol FastAPI runs on (via `uvicorn`) — the async equivalent of WSGI, not something you need to touch directly |
