# Scanrix Ingredient Safety Engine Documentation

Welcome to the technical documentation for the Scanrix Database-First Ingredient Safety Engine.

---

## 📚 Table of Contents

| Phase | Document | Description | Status |
|---|---|---|---|
| **Phase 1** | [Phase 1: Data Foundation](file:///Users/jazz/Documents/projects/SCANRIX/scanrix-backend/documentation/PHASE_1_DATA_FOUNDATION.md) | 5 MongoDB collections (`ingredients`, `aliases`, `facts`, `sources`, `ai_review_queue`), indexes, and seeding scripts. | ✅ Implemented |
| **Phase 2** | [Phase 2: Parsing & Matching](file:///Users/jazz/Documents/projects/SCANRIX/scanrix-backend/documentation/PHASE_2_PARSING_AND_MATCHING.md) | Bracket-aware text parsing, advisory allergen extraction, in-memory alias cache, and RapidFuzz typo matching. | ✅ Implemented |
| **Phase 3** | [Phase 3: Rule Engine](file:///Users/jazz/Documents/projects/SCANRIX/scanrix-backend/documentation/PHASE_3_RULE_ENGINE.md) | Deterministic risk evaluation, coverage calculation, multi-dimension scoring (`ruleset_v1.json`). | ✅ Implemented |
| **Phase 4** | [Phase 4: Scan Flow Integration](file:///Users/jazz/Documents/projects/SCANRIX/scanrix-backend/documentation/PHASE_4_SCAN_FLOW_INTEGRATION.md) | Connected into `/api/v1/scan` and `/analyze-text`, sub-50ms instant responses, 100% Flutter backward compatibility. | ✅ Implemented |
| **Phase 5** | [Phase 5: AI Fallback & Review Queue](file:///Users/jazz/Documents/projects/SCANRIX/scanrix-backend/documentation/PHASE_5_AI_FALLBACK_AND_REVIEW.md) | Sandboxing Gemini outputs with `verified: False`, Tier 4 evidence tagging, and admin approval/rejection endpoints. | ✅ Implemented |
| **Phase 6** | Phase 6: Golden Dataset Testing *(Upcoming)* | 100 golden products coverage and false-alarm regression suite. | ⏳ Next |
| **Phase 7** | Phase 7: Flutter Client Integration *(Upcoming)* | Multi-dimension findings UI, trust badges, coverage indicator. | ⏳ Planned |
| **Phase 8** | Phase 8: Compliance & Attributions *(Upcoming)* | Disclaimers, open data license compliance, and maintenance procedures. | ⏳ Planned |

---

## 🚀 Quick Commands Cheatsheet

### Database Setup
```bash
# Create MongoDB Atlas Indexes
python -m app.db.indexes

# Seed California Proposition 65
python -m scripts.seed_prop65

# Seed WHO IARC Monographs
python -m scripts.seed_iarc
```

### Run Unit Tests
```bash
# Parser Tests (Bracket splitting, allergens, percentages)
python tests/test_parser.py

# Matcher Tests (Exact, alias, and fuzzy typo matching)
python tests/test_matcher.py

# Rule Engine Tests (Determinism, coverage, severity rankings)
python tests/test_rule_engine.py
```
