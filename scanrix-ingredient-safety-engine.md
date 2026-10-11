# Scanrix - Ingredient Safety Engine: Implementation Plan

**Goal:** Replace AI-as-primary-verdict with a database-first ingredient engine. AI is only a fallback for unknown ingredients, and its output is stored as unverified.

**Stack:** Flutter (BLoC, Clean Architecture), FastAPI, MongoDB Atlas (free tier), Render (free), Gemini (fallback only)

**Constraints:** $0/month, no Docker, free tiers only

> Effort estimates are rough and assume one developer working part-time. Treat them as a starting point, not a commitment.

---

## 0. Feasibility check (do this first, about half a day)

Before writing code, confirm these against your current system. Tick each one.

| # | Check | How to verify | Result |
|---|---|---|---|
| 1 | Atlas storage headroom | Atlas dashboard, or `db.stats()` in mongosh. Free tier is 512 MB | [ ] |
| 2 | Render free-tier memory and cold starts | Render dashboard. Note the RAM limit and spin-down behavior | [ ] |
| 3 | Source files are downloadable and parseable | Manually download Prop 65, IARC list, CosIng. Open them and check columns | [ ] |
| 4 | Source licenses allow your use | Read each source's terms. Note attribution requirements | [ ] |
| 5 | Python libraries install cleanly | `pip install rapidfuzz pandas openpyxl` in your venv | [ ] |
| 6 | Current scan route structure | Find where Open Food Facts and Gemini are called today | [ ] |
| 7 | Current response schema the Flutter app expects | Note which fields the app already reads | [ ] |
| 8 | OCR output quality | Collect 10 real ingredient-label scans and look at the raw text | [ ] |

**Decision gate:** if checks 3 or 4 fail for a source, drop that source and continue with the others. Do not block the project on one source.

---

## 1. Target architecture (summary)

```
Raw sources -> Normalization -> Facts store (MongoDB) -> Rule engine -> Result
                                      ^
Scan flow:  barcode -> product cache / Open Food Facts -> parse ingredients
            -> alias match -> facts lookup -> rule engine -> response
            -> (unknown only) Gemini -> store as verified:false -> review queue
```

See `scanrix-architecture.md` for the full diagrams.

---

## 2. Backend structure (additions to your current layout)

```
backend/
  app/
    api/
      routes/
        scan.py                  # modify: call new engine
        admin_review.py          # new (optional): review AI proposals
    core/
      config.py                  # add: ruleset version, thresholds
    db/
      indexes.py                 # new: create indexes at startup or via script
    models/
      ingredient.py              # new
      alias.py                   # new
      fact.py                    # new
      source.py                  # new
      ai_review.py               # new
    schemas/
      scan_result.py             # modify/new: multi-dimension response
    crud/
      ingredient_crud.py         # new
      fact_crud.py               # new
    services/
      ingredient_parser.py       # new: clean and split label text
      ingredient_matcher.py      # new: exact + fuzzy match
      ingredient_db_service.py   # new: lookup orchestration
      rule_engine.py             # new: evaluate()
      ai_service.py              # existing: fallback only
    rules/
      ruleset_v1.json            # new: rules as data
  scripts/
    seed_prop65.py               # new
    seed_iarc.py                 # new
    seed_cosing.py               # new
    seed_additives.py            # new
    seed_allergens.py            # new
    common.py                    # shared parsing/upsert helpers
  data/
    raw/                         # downloaded source snapshots (git-ignored if large)
  tests/
    test_parser.py
    test_matcher.py
    test_rule_engine.py
    golden_products.json         # about 100 products with expected results
```

---

## 3. MongoDB collections and indexes

| Collection | Purpose | Key fields | Indexes |
|---|---|---|---|
| `sources` | Where data came from | name, version, license, url, retrieved_at | unique on (name, version) |
| `ingredients` | One doc per ingredient | canonical_name, cas_number, category | unique on canonical_name; sparse index on cas_number |
| `aliases` | Other names | normalized_alias, ingredient_id, alias_type | **unique on normalized_alias** |
| `facts` | Statements from sources | ingredient_id, source_id, dimension, value, severity, route, conditions, evidence_tier, verified | index on ingredient_id; compound on (ingredient_id, dimension) |
| `products` | Cached scanned products | barcode, name, category, ingredients_raw | unique on barcode |
| `scan_results` | Stored results (optional) | barcode, ruleset_version, dimensions, coverage | index on barcode |
| `ai_review_queue` | AI proposals awaiting review | ingredient_name, proposed_facts, status | index on status |

Design rules:
- Store **facts**, not verdicts. Verdicts are computed by the rule engine at query time.
- Keep only the fields you need from each source. Never import raw files whole.
- Every fact links to a source with version and retrieval date.

---

## 4. Phases

### Phase 1 - Data foundation (about 2 to 3 days)

**Tasks**
1. Create the Pydantic models and the `db/indexes.py` script.
2. Write `scripts/common.py` with helpers: `normalize_name()`, `upsert_ingredient()`, `upsert_alias()`, `upsert_fact()`.
3. Write the seed script for **one small source first** (Prop 65 or IARC).
4. Run it against a local or dev database, then check results by hand.

**Done when**
- Re-running the seed script creates no duplicates.
- You can query an ingredient by alias and see its facts and source.
- Storage used is well under the free-tier limit.

### Phase 2 - Parsing and matching (about 3 to 4 days)

**Tasks**
1. `ingredient_parser.py`: lowercase, remove "ingredients:" prefix, handle brackets and nested lists, split on commas, handle "may contain".
2. `ingredient_matcher.py`: exact alias match first, then `rapidfuzz` fuzzy match with three bands (accept / low-confidence suggestion / unknown). Start with thresholds you tune later.
3. Load the alias map into memory at app startup (small at this data size) with a DB fallback.
4. Unit tests with messy real label text from check #8 above.

**Done when**
- Exact matches resolve correctly on your sample labels.
- Fuzzy matches are flagged with a confidence value and never silently accepted at low scores.

### Phase 3 - Rule engine (about 2 to 3 days)

**Tasks**
1. Write `rules/ruleset_v1.json` with 5 to 10 rules (IARC Group 1 and 2A, EU prohibited, major allergens, Prop 65).
2. Implement `rule_engine.evaluate()` as a **pure function**: no DB or network calls inside.
3. Rules to include: severity ranking, worst-severity-per-dimension (do not add flags up), `no_downgrade` for serious rules, position and route adjustments for the rest.
4. Unit tests with fake ingredients.

**Done when**
- The same input always gives the same output.
- Unknown ingredients lower coverage and are never treated as safe.
- Wording is "contains an ingredient classified by..." and never "dangerous".

### Phase 4 - Integrate into the scan flow (about 2 days)

**Tasks**
1. In `scan.py`: after product fetch, run parser, matcher, facts lookup, then `evaluate()`.
2. Define the new response schema: findings per ingredient, per-dimension summary, coverage, evidence tier, ruleset version, disclaimer text.
3. Keep the old response fields working until the Flutter app is updated (backward compatibility), or version the endpoint.

**Done when**
- A real barcode scan returns the new structure end to end.
- Scans do not call Gemini when all ingredients are recognised.

### Phase 5 - AI fallback and review queue (about 1 to 2 days)

**Tasks**
1. Call `ai_service` only for ingredients still unknown after matching.
2. Store results as facts with `verified: false` and `evidence_tier: 4`, and add an entry to `ai_review_queue`.
3. Cache so the same unknown ingredient is never asked twice.
4. A simple way to review: a script or protected admin route that lists pending items and marks them approved or rejected.

**Done when**
- Unknown ingredients show as "AI-generated, unverified" in the response.
- Approved items are promoted to a higher tier only by your explicit action.

### Phase 6 - Testing and coverage (about 2 to 3 days, then ongoing)

**Tasks**
1. Build `golden_products.json`: about 100 real products (mix of food and cosmetics) with the expected findings.
2. Write a test runner that reports false alarms, misses, and coverage per product.
3. Add the most common unknown ingredients first (start with the top 500 to 1,000).
4. Tune rules and fuzzy thresholds.

**Done when**
- False alarms on the golden set are reviewed and explained or fixed.
- You have a coverage number you can track over time.

### Phase 7 - Flutter changes (about 3 to 4 days)

**Tasks**
1. Update the data models and BLoC states for the multi-dimension response.
2. UI: per-dimension sections, evidence-tier badge on each finding, coverage indicator ("18 of 21 recognised"), clear "not assessed" state for unknowns.
3. Show the disclaimer on the result screen.

**Done when**
- The result screen shows findings, trust tier, and coverage without any verdict implying "safe" for unrecognised ingredients.

### Phase 8 - Release readiness (about 1 to 2 days)

**Tasks**
1. Add attribution/credits for each source as required by its license.
2. Add the disclaimer: informational only, not medical advice.
3. Document how to re-run the seed scripts and when to do so.
4. Set a reminder to refresh the source data a few times a year.

---

## 5. Suggested MVP cut (if time is tight)

Build only this first, then expand:

- Sources: **Prop 65 + IARC + one allergen list**
- Rules: 5 rules
- Response: findings + coverage + disclaimer (skip scan_results storage)
- AI fallback: store as unverified, skip the review UI (review manually in Atlas)
- Flutter: one new result section, coverage indicator

Add CosIng, additives, and the full review flow after the MVP works end to end.

---

## 6. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Ingredient name matching is poor | Wrong or missed flags | Confidence values, test set, alias table that grows over time |
| Source file format changes | Seed script breaks | Keep raw snapshots, log runs, make scripts easy to re-run |
| Source license limits use | Legal risk | Check license first (Phase 0), add attribution |
| Free-tier limits (Atlas or Render) | Slowdowns or outages | Keep data small, in-memory alias map, check limits in Phase 0 |
| False alarms scare users | Users stop trusting the app | Hazard-vs-risk wording, severity from the rule engine, golden test set |
| False reassurance | Safety harm | Never label unknown as safe, always show coverage |
| AI hallucinations | Wrong info shown as fact | Always `verified: false`, tier 4, review before promotion |
| Liability if this becomes a business | Legal exposure | Disclaimer now, legal advice before any commercial launch |

---

## 7. Open decisions to confirm

1. Which markets matter first (India only, or also EU/US)? This decides whether FSSAI and Indian cosmetics rules come in early.
2. Food first, cosmetics first, or both in the MVP?
3. Do you want a user allergy profile in the MVP, or later?
4. Will you review AI proposals yourself, and how often?
5. Do you need old app versions to keep working (endpoint versioning)?

---

## 8. Total rough effort

| Phase | Estimate |
|---|---|
| 0. Feasibility | 0.5 day |
| 1. Data foundation | 2 to 3 days |
| 2. Parsing and matching | 3 to 4 days |
| 3. Rule engine | 2 to 3 days |
| 4. Scan flow integration | 2 days |
| 5. AI fallback and review | 1 to 2 days |
| 6. Testing and coverage | 2 to 3 days |
| 7. Flutter changes | 3 to 4 days |
| 8. Release readiness | 1 to 2 days |
| **Total** | **about 17 to 24 working days** |

---

## 9. Quick feasibility verdict template

Fill this in after Phase 0:

- Storage fits in Atlas free tier: yes / no
- Render handles the in-memory alias map: yes / no
- At least 2 sources downloadable and licensed for use: yes / no
- Current scan route can be extended without a rewrite: yes / no
- **Overall:** go / go with changes / no-go