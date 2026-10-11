import re
from datetime import datetime
from typing import Optional

def normalize_name(text: str) -> str:
    """
    Normalizes ingredient or chemical names for consistent matching.
    1. Lowercases text
    2. Strips square brackets / notes like '[Basis for listing changed...]' or '(Click here...)'
    3. Trims whitespace and removes extra internal spaces
    """
    if not text:
        return ""
    
    # Remove bracketed editorial notes like [Click here for basis...] or [Basis changed...]
    cleaned = re.sub(r"\[.*?\]", "", text)
    # Remove phrases like 'Delisted October 29, 1999'
    cleaned = re.sub(r"delisted\s+[a-zA-Z0-9,\s]+", "", cleaned, flags=re.IGNORECASE)
    # Convert to lowercase
    cleaned = cleaned.lower()
    # Normalize multiple whitespace characters to a single space
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Strip trailing commas, periods, hyphens
    cleaned = cleaned.strip(" ,.-;")
    
    return cleaned

async def upsert_source(
    db,
    name: str,
    version: str,
    license_type: str,
    url: Optional[str] = None,
    attribution: Optional[str] = None
) -> str:
    """
    Finds or creates a Source record (e.g. 'prop65', 'iarc').
    Returns the source document's string ID.
    """
    existing = await db.sources.find_one({"name": name, "version": version})
    if existing:
        return str(existing["_id"])
    
    new_doc = {
        "name": name,
        "version": version,
        "license": license_type,
        "url": url,
        "attribution": attribution,
        "retrieved_at": datetime.utcnow()
    }
    result = await db.sources.insert_one(new_doc)
    return str(result.inserted_id)

async def upsert_ingredient(
    db,
    canonical_name: str,
    cas_number: Optional[str] = None,
    category: Optional[str] = "chemical",
    description: Optional[str] = None
) -> str:
    """
    Finds or creates a canonical Ingredient master entity.
    Also automatically adds the canonical name as an alias.
    Returns the ingredient's string ID.
    """
    norm_name = normalize_name(canonical_name)
    if not norm_name:
        raise ValueError("Canonical name cannot be empty")
        
    # Check if ingredient already exists by canonical name
    existing = await db.ingredients.find_one({"canonical_name": norm_name})
    if existing:
        # If CAS number wasn't set earlier but is available now, update it
        if cas_number and not existing.get("cas_number"):
            await db.ingredients.update_one(
                {"_id": existing["_id"]},
                {"$set": {"cas_number": cas_number.strip()}}
            )
        return str(existing["_id"])
    
    # Clean CAS number if present (ignore dashes-only placeholder like '---')
    clean_cas = cas_number.strip() if cas_number and cas_number.strip() != "---" else None
    
    new_ingredient = {
        "canonical_name": norm_name,
        "cas_number": clean_cas,
        "category": category,
        "description": description,
        "created_at": datetime.utcnow()
    }
    result = await db.ingredients.insert_one(new_ingredient)
    ingredient_id = str(result.inserted_id)
    
    # Automatically add canonical name as its primary alias
    await upsert_alias(db, norm_name, ingredient_id, alias_type="canonical")
    
    # If CAS number exists, also add it as a searchable alias (e.g. '79-06-1')
    if clean_cas:
        await upsert_alias(db, clean_cas.lower(), ingredient_id, alias_type="cas")
        
    return ingredient_id

async def upsert_alias(
    db,
    alias: str,
    ingredient_id: str,
    alias_type: str = "common_name"
):
    """
    Adds an alias mapping to an ingredient, ignoring if the alias already exists.
    """
    norm_alias = normalize_name(alias)
    if not norm_alias:
        return
        
    existing = await db.aliases.find_one({"normalized_alias": norm_alias})
    if not existing:
        try:
            await db.aliases.insert_one({
                "normalized_alias": norm_alias,
                "ingredient_id": ingredient_id,
                "alias_type": alias_type,
                "created_at": datetime.utcnow()
            })
        except Exception:
            # Handles race conditions or unique index constraint gracefully
            pass

async def upsert_fact(
    db,
    ingredient_id: str,
    source_id: str,
    dimension: str,
    value: str,
    severity: str = "medium",
    evidence_tier: int = 2,
    verified: bool = True,
    route: Optional[str] = None,
    conditions: Optional[str] = None
):
    """
    Upserts a scientific or regulatory fact for an ingredient.
    Guarantees no duplicate fact per (ingredient_id, source_id, dimension).
    """
    fact_filter = {
        "ingredient_id": ingredient_id,
        "source_id": source_id,
        "dimension": dimension
    }
    fact_update = {
        "$set": {
            "value": value,
            "severity": severity,
            "evidence_tier": evidence_tier,
            "verified": verified,
            "route": route,
            "conditions": conditions,
            "updated_at": datetime.utcnow()
        },
        "$setOnInsert": {
            "created_at": datetime.utcnow()
        }
    }
    await db.facts.update_one(fact_filter, fact_update, upsert=True)
