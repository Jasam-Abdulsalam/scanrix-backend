# API_CONTRACT.md

Conventions shared by the backend and the Flutter client. The OpenAPI schema
(`/openapi.json`, browsable at `/docs`) is the source of truth for endpoints and
payloads; this file is the source of truth for the cross-cutting rules. If they disagree,
fix the code or this file in the same change.

**Status legend:** *Live* = the API already behaves this way. *Target* = new endpoints must
follow it; existing endpoints migrate additively and only after the Flutter team agrees.

## 1. Versioning and breaking changes
- All routes live under `/api/v1`. *Live.*
- Within a version, changes are additive only: new optional request fields, new response
  fields, new endpoints, new enum values the client may ignore.
- Breaking (needs `/api/v2` or an additive replacement): removing/renaming/retyping a field,
  making an optional field required, tightening validation, changing a status code or error
  `code`, changing auth requirements, changing pagination or ordering semantics.
- Clients must ignore unknown response fields and unknown enum values.
- Deprecating: mark `deprecated=True` in OpenAPI, add a `Deprecation` response header,
  keep the old version running until the oldest supported app version no longer uses it.
  Because mobile apps can't be force-updated, support at least two app release cycles
  [judgment].

## 2. Data formats
- JSON keys are `snake_case`. *Live.*
- Timestamps: ISO 8601 in UTC with a `Z` suffix, e.g. `2026-10-01T09:30:00Z`. Never local
  time, never epoch numbers. *Target* (verify existing fields before relying on it).
- Money: integer minor units plus an ISO 4217 code, e.g. `{"amount": 1999, "currency": "USD"}`.
  Never floats.
- IDs: opaque strings. Clients must not parse or order them. Barcodes are strings, never
  numbers (leading zeros matter).
- Nullable vs absent: a missing optional field and `null` are treated the same by the client.

## 3. Authentication
- `Authorization: Bearer <access_token>`. Tokens come from `POST /api/v1/auth/login` or
  `POST /api/v1/auth/google`. *Live.*
- Access tokens are short-lived (currently 30 minutes). On `401` the client re-authenticates;
  there is no refresh endpoint today.
- `401 Unauthorized`: missing, malformed, expired or invalid token, or bad credentials.
  Include `WWW-Authenticate: Bearer`.
- `403 Forbidden`: authenticated, but not allowed (e.g. someone else's resource).
- `404` may be used instead of `403` for resources whose existence must not leak [judgment].

## 4. Errors (RFC 9457)
*Target.* Today handlers return FastAPI's `{"detail": "..."}`; switching is a client-visible
change and needs coordination.

Content type `application/problem+json`:

```json
{
  "type": "https://api.scanrix.app/problems/scan-limit-reached",
  "title": "Daily scan limit reached",
  "status": 429,
  "detail": "You have used all 10 scans for today.",
  "instance": "/api/v1/scan/",
  "code": "scan_limit_reached",
  "request_id": "b1f0c2e4-..."
}
```

- `code` is stable and machine-readable (`snake_case`); the client branches on `code`, never
  on `title` or `detail` text. Codes are never renamed or reused.
- Validation failures: `422`, `code: "validation_error"`, with `errors: [{"field": "email",
  "code": "invalid_email", "message": "..."}]`.
- Rate limiting: `429` with `Retry-After` (seconds).
- Unexpected errors: `500`, `code: "internal_error"`, no internals in the body. The
  `request_id` lets support find the log line.

## 5. Pagination (cursor)
*Target for every new list endpoint.*

Request: `GET /api/v1/history?limit=20&cursor=<opaque>`. Default `limit` 20, max 100;
values above 100 are rejected with `422` (not silently clamped).

```json
{ "items": [ ... ], "next_cursor": "eyJ...", "has_more": true }
```

- `next_cursor` is `null` when `has_more` is `false`. Cursors are opaque, signed or encoded
  by the server, valid for a limited time, and must not be built or parsed by the client.
- Ordering is stable and deterministic (e.g. `scanned_at desc, id desc`).
- `GET /history` and `GET /favorites` use this envelope (the app is not released yet, so
  `GET /history` was moved from a bare list to the envelope in one step; do the opt-in
  route/parameter dance for any list that has live clients).
- Invalid cursor: `422` with `detail.code = "invalid_cursor"`. Implemented in `app/core/pagination.py`
  (cursor = last row's sort value + `_id`, base64url JSON, not signed).

## 6. Idempotency
- Unsafe operations that clients may retry (creating resources, uploads, anything with
  side effects) accept `Idempotency-Key: <uuid>`.
- Same key + same request body within 24 h: return the stored original response (same status),
  and add `Idempotent-Replayed: true`. Same key + different body: `422`
  `code: "idempotency_key_reuse"`. Concurrent duplicate while the first is running: `409`
  `code: "request_in_progress"`.
- Keys are scoped per user. `GET`, `PUT` and `DELETE` are naturally idempotent and ignore the
  header.

## 7. Request tracing
- The client may send `X-Request-ID` (UUID). If absent the server generates one. The server
  always returns it in the `X-Request-ID` response header and in error bodies, and logs it
  on every line. Clients should log it with any error they report.

## 8. File uploads (pre-signed URLs)
*Target.* Large/binary uploads don't pass through the API server:
1. `POST /api/v1/uploads` `{"content_type": "image/jpeg", "size_bytes": 123456, "purpose":
   "profile_photo"}` returns `{"upload_id", "upload_url", "expires_at", "headers"}`; the
   server validates type and size limits first.
2. The client `PUT`s the bytes straight to `upload_url` (object storage, e.g. S3 pre-signed URL).
3. The client references `upload_id` in the follow-up call (e.g. profile update); the server
   verifies the object exists, then attaches it.
- URLs expire in minutes; the allowed content type and max size are enforced by the signature.
- Legacy: `POST /auth/me/photo` (multipart, via Cloudinary) stays until the client migrates.

## 9. Long-running work (`202` + job resource)
*Target.* Anything that may exceed a few seconds returns `202 Accepted` with a `Location`
header and a job body, instead of blocking:

```json
{ "id": "job_...", "status": "queued", "status_url": "/api/v1/jobs/job_..." }
```

- `GET /api/v1/jobs/{id}` returns `status`: `queued` | `running` | `succeeded` | `failed`,
  plus `result` (or a link to the created resource) or an RFC 9457 `error`. Terminal states
  are `succeeded` and `failed`. Include `Retry-After` while pending.
- Job ids are per-user: other users get `404`.
- Legacy equivalent: `POST /scan/` returns the product with `verdict: "analyzing"` and the
  client polls `GET /products/{barcode}` until `verdict` is no longer `analyzing`
  (final values: `safe`, `caution`, `avoid`, plus terminal `error` / `unknown`). This keeps working; new long tasks use the job resource.
  The value `safe` is kept for compatibility but must be *shown* as "No Known Concerns" (rows: "No flags"): it means "no hazard found in our data", not a health guarantee.

## 10. OpenAPI as the source of truth
- Every endpoint declares `response_model`, status codes (`responses=`), a summary and tags.
- The schema is generated from code, never hand-edited. Pydantic field descriptions and
  examples are the documentation.
- CI exports `openapi.json` and diffs it against the previous release to detect breaking
  changes (section 1) before merge. *Target.*
- The Flutter client's models should be generated from or checked against this schema, not
  hand-copied.

## 11. Opt-in AI verdict and credits (`/api/v1/ai/*`)
The "Get AI verdict" button, for products our database cannot judge well. The AI result is an
**unverified estimate shown beside the database result; it never replaces it.**

When to show the button (client rule): `safety_engine.coverage < 0.7` or verdict `unknown`.

`POST /api/v1/ai/analyze-product`, body: exactly one of
`{ "barcode": "..." }` (a scanned product) or `{ "ingredients_text": "...", "category": "food" | "cosmetic" | "household" }` (OCR flow).

Response `200` (`AIAnalyzeResponse`): `verdict` (`good` | `caution` | `avoid` | `unknown`), `score` 0-100,
`summary`, `concerns[]` (`ingredient`, `effect`), `positives[]`, `certainty` (`well_known` | `uncertain` | `unknown`),
`adjusted_by_database` (true when our database hazards lowered the AI's verdict), `verified: false`,
`source: "ai"`, `cached`, `credits_remaining`, `generated_at`, `disclaimer`.
Show `good` as "looks fine / low concern", never "safe".

Errors (`detail` is an object with a stable `code`):
- `404` product not found.
- `422` `ingredients_missing`: the product has no ingredient list. Ask the user to scan the ingredients label (OCR), then call again with `ingredients_text`.
- `429` `ai_credits_exhausted`: includes `resets_at` and a `Retry-After` header.
- `503` `ai_unavailable`: the user was not charged and nothing was saved. Retry later.

Credits: `AI_CREDITS_PER_WEEK` (default 6) per user per ISO week (resets Monday 00:00 UTC), shared by all
AI features (later also "View alternatives"). A new analysis costs 1 credit; a result that already
exists (cache hit, same product and ingredient list) is free. A failed call is refunded.
`GET /api/v1/ai/credits` -> `{ limit, remaining, resets_at }`.

Client notes: disable the button while a call is running (a double tap on the same product can charge twice);
`GET /products/{barcode}` returns the cached `ai_analysis` (no credit, never calls the AI) so a reopened
product shows it again.

Server rules: guardrail "hazards win" (the AI verdict is never better than a hazard in our database;
score capped at 85; no `good` from pure guesswork); AI output is validated and rejected, never repaired;
results live in `ai_product_analyses` (TTL `AI_ANALYSIS_TTL_DAYS`, default 90), never in the safety tables.

## 12. Scan history (`/api/v1/history`)
Auth required. Only barcode scans (`POST /scan/`) are recorded; label (OCR) scans are not.

| Method | Path | Result |
|---|---|---|
| GET | `/history/?limit=20&cursor=` | `200` `{items, next_cursor, has_more}`, newest first. `limit` 1-100 (default 20), otherwise `422`. |
| GET | `/history/count` | `200` `{count}`: entries currently in the caller's history (drops when entries are deleted or cleared). |
| DELETE | `/history/{id}` | `204`. `404` if the entry does not exist **or belongs to another user** (same answer, no leak). |
| DELETE | `/history/` | `204`. Deletes all of the caller's entries (idempotent: empty history is still `204`). |

Each item: `id`, `user_id`, `product_id`, `verdict` (as shown at scan time), `personalized_score`
(always null for now), `scanned_at` (UTC, **no zone suffix** in the JSON), and **`product`**:
`{barcode, name, brand, category, image_url}` or `null` if the product no longer exists.
Clients open the product with `GET /products/{barcode}` (which re-evaluates, so the verdict there
can differ from the stored one). Index: `(user_id, scanned_at desc, _id desc)`.

## 13. Saved products (`/api/v1/favorites`)
Auth required. One row per (user, product), unique index, so saving is idempotent and race-safe.

| Method | Path | Result |
|---|---|---|
| PUT | `/favorites/{barcode}` | `204`. Safe to repeat (also at the cap). `404` unknown barcode. `409` `favorites_limit_reached` at `FAVORITES_MAX_PER_USER` (default 500; soft cap, two simultaneous adds can overshoot by 1). |
| DELETE | `/favorites/{barcode}` | `204`, also when it was not saved. |
| GET | `/favorites/?limit=20&cursor=` | `200` `{items, next_cursor, has_more}`, newest saved first. Items: `id, barcode, name, brand, category, image_url, verdict, overall_score, added_at`. `verdict`/`overall_score` are the product's **stored** values; a saved product that no longer exists is left out, so a page may hold fewer than `limit` rows. |
| GET | `/favorites/barcodes` | `200` `{barcodes: [...]}`: every saved barcode (bounded by the cap), to fill hearts in one call. |

Deleting the account (`DELETE /auth/me`) deletes the user's favorites too.
