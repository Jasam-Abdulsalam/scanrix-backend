import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

DEFAULT_RULESET_PATH = Path(__file__).resolve().parent.parent / "rules" / "ruleset_v1.json"

# Fact dimensions that describe what an ingredient IS or does. They never raise severity,
# flags or an evidence-tier badge: a function is information, not a warning.
INFO_DIMENSIONS = {"function", "health_effects"}

def collect_information(fact: Dict[str, Any], functions: List[str], effects: List[str]) -> None:
    """Adds an informational fact to the finding's `functions` or `effects` list (no duplicates)."""
    if fact.get("dimension") == "health_effects":
        items, target = str(fact.get("conditions") or "").split(";"), effects
    else:
        items, target = str(fact.get("value", "")).lower().split(","), functions
    for item in (i.strip() for i in items):
        if item and item not in target:
            target.append(item)


class IngredientFinding(BaseModel):
    raw_name: str = Field(..., description="The name as scanned from the packaging")
    canonical_name: Optional[str] = Field(None, description="Standardized chemical name if matched")
    matched: bool = Field(..., description="True if recognised in the database")
    match_type: str = Field("unknown", description="'exact' | 'fuzzy' | 'suggested' | 'unknown'")
    confidence: float = Field(0.0, description="Matching confidence score (0.0 to 1.0)")
    severity: str = Field("none", description="Worst severity for this ingredient: none | low | medium | high | critical")
    evidence_tier: Optional[int] = Field(None, description="1=Gov ban, 2=IARC/Prop65, 3=Panel, 4=AI unverified")
    flags: List[str] = Field(default_factory=list, description="Descriptive labels of safety classifications")
    functions: List[str] = Field(default_factory=list, description="What the ingredient is used for (e.g. 'emulsifier'); informational only")
    effects: List[str] = Field(default_factory=list, description="Known effects of the pure substance in plain English (e.g. 'Can irritate the skin'); informational only, never changes the verdict")
    facts: List[Dict[str, Any]] = Field(default_factory=list, description="Raw scientific facts attached to this ingredient")

class DimensionSummary(BaseModel):
    dimension: str = Field(..., description="Risk category: cancer_class | developmental | reproductive | etc.")
    worst_severity: str = Field("none", description="Highest severity observed within this dimension")
    flagged_ingredients: List[str] = Field(default_factory=list, description="Names of ingredients triggering this dimension")
    findings_count: int = Field(0, description="Total number of findings in this dimension")

class EvaluationResult(BaseModel):
    ruleset_version: str = Field(..., description="Version of the ruleset used for evaluation")
    coverage: float = Field(..., description="Proportion of ingredients recognised (0.0 to 1.0)")
    recognised_count: int = Field(..., description="Number of recognised ingredients")
    total_count: int = Field(..., description="Total ingredients assessed")
    overall_severity: str = Field("none", description="Worst severity across all evaluated dimensions")
    dimensions: Dict[str, DimensionSummary] = Field(default_factory=dict, description="Summary broken down by safety dimension")
    findings: List[IngredientFinding] = Field(default_factory=list, description="Per-ingredient detailed findings")
    declared_allergens: List[str] = Field(default_factory=list, description="Allergens the label states it CONTAINS ('Contains: milk, soy')")
    may_contain_allergens: List[str] = Field(default_factory=list, description="Allergens the label says it MAY contain (cross-contact advisory)")
    disclaimer: str = Field(..., description="Mandatory informational disclaimer text")

class RuleEngine:
    """
    Deterministic safety rule engine.
    Pure evaluation logic: NO database or network calls inside evaluate().
    Computes multi-dimensional risk, coverage ratio, and severity rankings.
    """

    def __init__(self, ruleset_path: Optional[Path] = None):
        path = ruleset_path or DEFAULT_RULESET_PATH
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                self.ruleset = json.load(f)
        else:
            self.ruleset = {
                "version": "1.0.0",
                "disclaimer": "Informational only.",
                "severity_ranks": {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4},
                "dimensions": [],
                "rules": []
            }

        self.severity_ranks: Dict[str, int] = self.ruleset.get(
            "severity_ranks",
            {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        )

    def _rank_severity(self, sev: str) -> int:
        return self.severity_ranks.get(sev.lower(), 0)

    def evaluate(
        self,
        ingredients_data: List[Dict[str, Any]],
        ruleset_override: Optional[Dict[str, Any]] = None
    ) -> EvaluationResult:
        """
        Pure function: Evaluates a list of parsed ingredients with their matched facts.

        Expected format of each item in ingredients_data:
        {
            "raw_name": str,
            "canonical_name": Optional[str],
            "matched": bool,
            "match_type": str,       # 'exact' | 'fuzzy' | 'suggested' | 'unknown'
            "confidence": float,
            "facts": List[dict]      # List of fact documents from MongoDB
        }
        """
        ruleset = ruleset_override or self.ruleset
        rules = ruleset.get("rules", [])
        known_dimensions = ruleset.get("dimensions", [
            "cancer_class", "developmental", "reproductive", "regulatory", "allergen", "irritation"
        ])

        total_count = len(ingredients_data)
        recognised_count = 0
        findings: List[IngredientFinding] = []

        # Initialize dimension summaries
        dim_summaries: Dict[str, DimensionSummary] = {
            dim: DimensionSummary(dimension=dim, worst_severity="none", flagged_ingredients=[], findings_count=0)
            for dim in known_dimensions
        }

        overall_worst_rank = 0
        overall_worst_sev = "none"

        for item in ingredients_data:
            raw_name = item.get("raw_name", "Unknown")
            canonical = item.get("canonical_name")
            matched = item.get("matched", False)
            match_type = item.get("match_type", "unknown")
            confidence = item.get("confidence", 0.0)
            facts = item.get("facts", [])

            if matched:
                recognised_count += 1

            ing_worst_rank = 0
            ing_worst_sev = "none"
            ing_flags: List[str] = []
            ing_functions: List[str] = []
            ing_effects: List[str] = []
            min_evidence_tier: Optional[int] = None

            # Evaluate facts against ruleset
            for fact in facts:
                fact_dim = fact.get("dimension")
                fact_val = str(fact.get("value", "")).lower()
                fact_sev = fact.get("severity", "medium")
                fact_tier = fact.get("evidence_tier", 2)

                if fact_dim in INFO_DIMENSIONS:
                    collect_information(fact, ing_functions, ing_effects)
                    continue

                if min_evidence_tier is None or fact_tier < min_evidence_tier:
                    min_evidence_tier = fact_tier

                # Check if any rule matches this fact
                rule_matched = False
                for rule in rules:
                    if rule.get("dimension") == fact_dim:
                        match_pattern = str(rule.get("match_value", "")).lower()
                        # Direct or substring match
                        if match_pattern in fact_val or fact_val in match_pattern:
                            rule_sev = rule.get("severity", fact_sev)
                            rule_rank = self._rank_severity(rule_sev)
                            rule_label = rule.get("label", f"{fact_dim}: {fact_val}")

                            ing_flags.append(rule_label)
                            if rule_rank > ing_worst_rank:
                                ing_worst_rank = rule_rank
                                ing_worst_sev = rule_sev

                            # Update dimension summary
                            if fact_dim in dim_summaries:
                                d_summary = dim_summaries[fact_dim]
                                d_summary.findings_count += 1
                                if raw_name not in d_summary.flagged_ingredients:
                                    d_summary.flagged_ingredients.append(raw_name)
                                if rule_rank > self._rank_severity(d_summary.worst_severity):
                                    d_summary.worst_severity = rule_sev

                            rule_matched = True

                # Fallback if no specific rule matched but fact has severity
                if not rule_matched and fact_dim and self._rank_severity(fact_sev) > 0:
                    f_rank = self._rank_severity(fact_sev)
                    if f_rank > ing_worst_rank:
                        ing_worst_rank = f_rank
                        ing_worst_sev = fact_sev

                    if fact_dim in dim_summaries:
                        d_summary = dim_summaries[fact_dim]
                        d_summary.findings_count += 1
                        if raw_name not in d_summary.flagged_ingredients:
                            d_summary.flagged_ingredients.append(raw_name)
                        if f_rank > self._rank_severity(d_summary.worst_severity):
                            d_summary.worst_severity = fact_sev

            # Track overall worst severity across entire product
            if ing_worst_rank > overall_worst_rank:
                overall_worst_rank = ing_worst_rank
                overall_worst_sev = ing_worst_sev

            findings.append(
                IngredientFinding(
                    raw_name=raw_name,
                    canonical_name=canonical,
                    matched=matched,
                    match_type=match_type,
                    confidence=confidence,
                    severity=ing_worst_sev,
                    evidence_tier=min_evidence_tier,
                    flags=ing_flags,
                    functions=ing_functions,
                    effects=ing_effects,
                    facts=facts
                )
            )

        # Calculate coverage (recognised / total)
        coverage = round(recognised_count / total_count, 2) if total_count > 0 else 0.0

        return EvaluationResult(
            ruleset_version=ruleset.get("version", "1.0.0"),
            coverage=coverage,
            recognised_count=recognised_count,
            total_count=total_count,
            overall_severity=overall_worst_sev,
            dimensions=dim_summaries,
            findings=findings,
            disclaimer=ruleset.get(
                "disclaimer",
                "This analysis is for informational purposes only and does not constitute medical or health advice."
            )
        )

# Singleton rule engine instance
rule_engine = RuleEngine()
