# Scanrix - Ingredient Safety Architecture

Database-first ingredient knowledge base. AI is used only as a fallback for unknown ingredients, and its output is stored as unverified.

How to use in Notion: type `/code`, set language to **Mermaid**, paste one diagram per block. Or import this file via Notion's Import > Markdown.

---

## 1. Layered architecture

```mermaid
flowchart TB
    subgraph L1["Layer 1 - Raw source snapshots"]
        S1["EU CosIng"]
        S2["IARC"]
        S3["Prop 65"]
        S4["Food additives - EFSA / FSSAI"]
        S5["Allergen lists"]
    end

    subgraph L2["Layer 2 - Normalization"]
        N1["Clean names, CAS numbers, E-numbers"]
        N2["Entity resolution - merge duplicates"]
    end

    subgraph L3["Layer 3 - Facts store - MongoDB"]
        F1["ingredients"]
        F2["aliases"]
        F3["facts"]
    end

    subgraph L4["Layer 4 - Rule engine"]
        R1["Versioned rules and weights"]
        R2["Context: position, product type, user profile"]
    end

    subgraph L5["Layer 5 - Result"]
        O1["Multi-dimension result plus coverage"]
    end

    S1 --> N1
    S2 --> N1
    S3 --> N1
    S4 --> N1
    S5 --> N1
    N1 --> N2
    N2 --> F1
    N2 --> F2
    N2 --> F3
    F1 --> R1
    F2 --> R1
    F3 --> R1
    R2 --> R1
    R1 --> O1
```

---

## 2. Seeding pipeline (run manually or on a schedule, not at app startup)

```mermaid
flowchart LR
    A["Download source file"] --> B["Save raw snapshot - version, date, license"]
    B --> C["Parse and keep needed fields only"]
    C --> D["Normalize names, CAS, E-numbers"]
    D --> E{"Ingredient exists?"}
    E -- "Yes" --> F["Upsert facts and aliases"]
    E -- "No" --> G["Create ingredient, then facts and aliases"]
    F --> H["Log run: counts, errors, source version"]
    G --> H
```

---

## 3. Scan flow (runtime)

```mermaid
sequenceDiagram
    participant App as Flutter app
    participant API as FastAPI
    participant DB as MongoDB
    participant OFF as Open Food Facts API
    participant AI as Gemini

    App->>API: Send barcode or OCR text
    API->>DB: Product cached?
    alt Not cached
        API->>OFF: Fetch product by barcode
        OFF-->>API: Ingredient text
        API->>DB: Cache product
    end
    API->>API: Parse and normalize ingredients
    API->>DB: Lookup aliases, then facts
    DB-->>API: Matches and facts
    opt Unknown ingredients remain
        API->>AI: Ask about unknown ones only
        AI-->>API: Draft info
        API->>DB: Save as verified false and add to review queue
    end
    API->>API: Rule engine builds result and coverage
    API-->>App: Dimensions, evidence tiers, coverage, disclaimer
```

---

## 4. Ingredient matching

```mermaid
flowchart TD
    A["Raw ingredient text"] --> B["Clean: lowercase, strip brackets, split nested"]
    B --> C{"Exact match in aliases?"}
    C -- "Yes" --> D["Matched - high confidence"]
    C -- "No" --> E["Fuzzy match - rapidfuzz"]
    E --> F{"Score high enough?"}
    F -- "Very high" --> G["Matched - flag as fuzzy"]
    F -- "Medium" --> H["Suggest best guess, mark low confidence"]
    F -- "Low" --> I["Unknown ingredient"]
    I --> J["AI fallback - verified false"]
    J --> K["Review queue"]
    D --> L["Continue to facts lookup"]
    G --> L
    H --> L
```

---

## 5. Data model (entities)

```mermaid
erDiagram
    SOURCE ||--o{ FACT : provides
    INGREDIENT ||--o{ ALIAS : has
    INGREDIENT ||--o{ FACT : has
    PRODUCT ||--o{ SCAN_RESULT : produces
    RULESET ||--o{ SCAN_RESULT : scores
    INGREDIENT ||--o{ AI_REVIEW_QUEUE : proposed_for

    SOURCE {
        string id PK
        string name
        string version
        string license
        string url
        date retrieved_at
    }

    INGREDIENT {
        string id PK
        string canonical_name
        string cas_number
        string category
    }

    ALIAS {
        string normalized_alias PK
        string ingredient_id FK
        string alias_type
    }

    FACT {
        string id PK
        string ingredient_id FK
        string source_id FK
        string dimension
        string value
        string severity
        string route
        string conditions
        string evidence_tier
        boolean verified
    }

    PRODUCT {
        string barcode PK
        string name
        string category
        string ingredients_raw
    }

    RULESET {
        string version PK
        string weights
        string thresholds
        date created_at
    }

    SCAN_RESULT {
        string id PK
        string barcode FK
        string ruleset_version FK
        string dimensions
        float coverage
        date created_at
    }

    AI_REVIEW_QUEUE {
        string id PK
        string ingredient_name
        string proposed_facts
        string status
    }
```

Notes:
- `ALIAS.normalized_alias` should have a **unique index**.
- `FACT.dimension` holds values like `regulatory`, `cancer_class`, `allergen`, `irritation`.
- `FACT.evidence_tier` is 1 to 4 (see diagram 6).

---

## 6. Evidence trust tiers and result dimensions

```mermaid
flowchart TB
    subgraph T["Evidence tiers - highest trust first"]
        T1["Tier 1 - Regulatory bans and limits"]
        T2["Tier 2 - IARC-type classifications, Prop 65"]
        T3["Tier 3 - Expert reviews: CIR, SCCS"]
        T4["Tier 4 - AI generated, unverified"]
        T1 --> T2 --> T3 --> T4
    end

    subgraph R["Result returned to the app"]
        D1["Regulatory status"]
        D2["Cancer classification"]
        D3["Allergens"]
        D4["Irritation"]
        D5["Coverage - recognised / total"]
        D6["Evidence tier shown per finding"]
        D7["Disclaimer"]
    end

    T --> R
```

---

## 7. Quality loop

```mermaid
flowchart LR
    A["Test set - about 100 real products with expected outcomes"] --> B["Run scans through the engine"]
    B --> C{"False alarms or misses?"}
    C -- "Yes" --> D["Adjust rules, weights, or add missing ingredients"]
    D --> B
    C -- "No" --> E["Check coverage metric"]
    E --> F{"Coverage good enough?"}
    F -- "No" --> G["Add most common unknown ingredients - top 500 to 1000 first"]
    G --> B
    F -- "Yes" --> H["Release with disclaimer"]
```

---

## Key principles

1. Layer the system: raw snapshots, normalization, facts, rule engine, result. Keep each layer separate and versioned.
2. Separate alias collection with a unique index; use rapidfuzz for typos and suggest low-confidence matches instead of accepting them silently.
3. Return several dimensions (regulatory, cancer classification, allergens, irritation, coverage), not one verdict.
4. Rank evidence by trust and show the tier in the UI.
5. Treat AI output as unverified: store with `verified: false`, cache, queue for review.
6. Start with the top 500 to 1,000 common ingredients and track a coverage metric.
7. Keep a test set of about 100 real products with expected outcomes.
8. Show a clear disclaimer: informational, not medical advice.