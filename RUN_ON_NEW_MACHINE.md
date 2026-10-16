# Run Scanrix on another machine (testing checklist)

Copy-paste in order. Everything runs in Docker, with a **local** MongoDB, so no Atlas / IP allowlist is needed.

## Quick path: already set up once, just pulled new code
```bash
# backend (in scanrix-backend)
git pull origin dev
docker compose up -d --build app                       # new code is baked into the image
docker compose exec app python -m app.db.indexes       # NEW indexes (history paging, favorites): required
docker compose restart app
# seeds: only if a pull added/changed one (see step 4); they are safe to re-run

# app (in Scanrix-frontend)
git pull origin mini
fvm flutter pub get                                    # new packages (bloc_concurrency)
fvm flutter run
```
**The app and backend must be updated together:** `GET /history/` now returns `{items, next_cursor, has_more}`
instead of a list, so an old app against the new backend (or the reverse) shows an error on History.
Also check `BASE_URL` in the app's `.env` still matches this machine's LAN IP (it changes per network).

## 0. Prerequisites
- Docker Desktop running
- Git, and (for the app) FVM + Flutter 3.47.5 (`fvm install` reads `.fvmrc`)

## 1. Get the code
```bash
git clone https://github.com/Jasam-Abdulsalam/scanrix-backend.git
cd scanrix-backend
git checkout dev

# in another folder
git clone https://github.com/Jasam-Abdulsalam/Scanrix-frontend.git
cd Scanrix-frontend
git checkout mini
```

## 2. Create the backend `.env` (not in git)
```bash
cd scanrix-backend
cp .env.example .env
```
Edit `.env`. Only these matter for local Docker:

| Key | Value |
|---|---|
| `SECRET_KEY` | any long random string (`openssl rand -hex 32`) |
| `DATABASE_NAME` | `SCANRIX` |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | your keys, needed only for "Get AI verdict" |
| `AI_FALLBACK_ENABLED` | `false` |

Optional keys (defaults are fine): `AI_CREDITS_PER_WEEK=6`, `FAVORITES_MAX_PER_USER=500`.

`MONGODB_URL` and the Redis URL are overridden by `docker-compose.yml` (local Mongo + local Redis), so leave them.

## 3. Start the backend
```bash
docker compose up -d --build
docker compose ps                 # app, mongo, redis, srh = running
docker compose logs -f app        # wait for "Application startup complete", Ctrl+C to leave
curl http://localhost:8000/health
```
API docs: http://localhost:8000/docs

## 4. Load the data (once per Docker volume, keep this order)
```bash
docker compose exec app python -m app.db.indexes
docker compose exec app python -m scripts.seed_iarc
docker compose exec app python -m scripts.seed_prop65
docker compose exec app python -m scripts.seed_off
docker compose exec app python -m scripts.seed_aliases
docker compose exec app python -m scripts.seed_cosing
docker compose exec app python -m scripts.seed_eu_inventory
docker compose exec app python -m scripts.seed_echa_clp
docker compose exec app python -m scripts.seed_fssai
docker compose restart app        # reload the alias cache
```
All seeds are safe to re-run (they upsert, never duplicate). Re-run only the newer ones after a pull.

Check the data landed:
```bash
docker compose exec -T mongo mongosh --quiet SCANRIX --eval 'printjson({ingredients:db.ingredients.countDocuments(),aliases:db.aliases.countDocuments(),facts:db.facts.countDocuments(),sources:db.sources.distinct("name")})'
```
Expect roughly: ingredients ~8.5k+ (more after the EU inventory), `sources` includes `iarc, prop65, openfoodfacts_taxonomies, cosing_*, eu_cosmetic_inventory_2006, echa_clp*, fssai*`.

## 5. Try the API (curl)
```bash
# register + login (copy the access_token)
curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"me@test.com","password":"secret123","name":"Me"}'
curl -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"me@test.com","password":"secret123"}'

TOKEN=paste_access_token_here

# analyse a label by text
curl -X POST localhost:8000/api/v1/scan/analyze-text -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"ingredients_text":"Sugar, Wheat Flour, Palm Oil, Salt","category":"food"}'

# AI verdict (uses 1 credit; call twice, 2nd must say "cached": true)
curl -X POST localhost:8000/api/v1/ai/analyze-product -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"ingredients_text":"Zorbex-9, Sugar, Mystery Gum","category":"food"}'
curl localhost:8000/api/v1/ai/credits -H "Authorization: Bearer $TOKEN"
```

### History and saved products (needs a product in the database)
```bash
# scan a barcode (also creates a history entry). Use a real one, e.g. a biscuit pack you have.
curl -X POST localhost:8000/api/v1/scan/ -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"barcode":"8901063010154"}'

# history: first page of 2, then follow next_cursor
curl "localhost:8000/api/v1/history/?limit=2" -H "Authorization: Bearer $TOKEN"
curl "localhost:8000/api/v1/history/?limit=2&cursor=PASTE_NEXT_CURSOR" -H "Authorization: Bearer $TOKEN"
curl -X DELETE localhost:8000/api/v1/history/PASTE_ENTRY_ID -H "Authorization: Bearer $TOKEN"   # 204; again = 404

# saved products (barcode of a product that exists)
curl -X PUT    localhost:8000/api/v1/favorites/8901063010154 -H "Authorization: Bearer $TOKEN"   # 204, safe to repeat
curl           localhost:8000/api/v1/favorites/barcodes       -H "Authorization: Bearer $TOKEN"
curl "localhost:8000/api/v1/favorites/?limit=2"               -H "Authorization: Bearer $TOKEN"
curl -X DELETE localhost:8000/api/v1/favorites/8901063010154 -H "Authorization: Bearer $TOKEN"   # 204, also if not saved
```
Expected: `limit` outside 1-100 gives `422`; a made-up `cursor` gives `422 invalid_cursor`; an unknown barcode on PUT gives `404`.

Expected AI errors: `422 ingredients_missing`, `429 ai_credits_exhausted` (after 6 per week), `503 ai_unavailable` (no/invalid key; not charged).

## 6. Run the Flutter app
```bash
cd Scanrix-frontend
cp .env.example .env
```
Set `BASE_URL` in `.env` to this machine's **LAN IP** (phone and laptop on the same Wi-Fi):
```bash
ipconfig getifaddr en0            # macOS Wi-Fi IP, e.g. 192.168.1.50
# BASE_URL=http://192.168.1.50:8000/api/v1
```
```bash
fvm install
fvm flutter pub get
fvm flutter run
fvm flutter test                  # only test/widget_test.dart fails (known, needs Google Sign-In mock)
```

### What to try in the app
Scan a product, open History (rows appear, swipe left deletes, "Clear all" asks first), tap the heart on a product page
(then Profile -> Favorites shows it and the count), swipe a saved row to remove it. Scroll a long list: the next page loads near the end.

## 7. Useful commands
```bash
docker compose logs -f app                       # backend logs
docker compose restart app                       # after seeding
docker compose up -d --build app                 # after pulling new code
docker compose down                              # stop, KEEPS data
docker compose down -v                           # stop and WIPE data (then redo step 4)
docker compose exec app python -m scripts.top_unknowns --limit 20   # most-scanned unrecognised ingredients
```

## Troubleshooting
- **Port 8000 busy:** change the left side of `"8000:8000"` in `docker-compose.yml`, and `BASE_URL`.
- **Phone can't reach the backend:** wrong LAN IP, different Wi-Fi, or the Mac firewall blocking Docker.
- **Every scan says "not assessed":** seeds not run, or `docker compose restart app` missing after seeding.
- **History/Favorites show an error or "Product no longer available" on every row:** the backend image is old; run `docker compose up -d --build app` (and the indexes command).
- **Favorites/History slow or unsorted with lots of data:** the indexes were not created; run `docker compose exec app python -m app.db.indexes`.
- **"Get AI verdict" gives 503:** `GROQ_API_KEY` / `GEMINI_API_KEY` missing in `.env`; rebuild/restart `app` after editing it.
- Never paste `.env` contents or connection strings into chats or commits.
