from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.services.rule_engine import EvaluationResult, IngredientFinding, DimensionSummary

class ScanResultResponse(BaseModel):
    """
    Standardized API response for ingredient safety evaluation.
    Used both in barcode scans and direct OCR text analysis.
    """
    ruleset_version: str
    coverage: float = Field(..., description="Proportion of recognised ingredients (0.0 to 1.0)")
    recognised_count: int
    total_count: int
    overall_severity: str = Field(..., description="'none' | 'low' | 'medium' | 'high' | 'critical'")
    dimensions: Dict[str, DimensionSummary]
    findings: List[IngredientFinding]
    disclaimer: str
    unknown_ingredients: List[str] = Field(default_factory=list, description="Ingredients queued for AI review")

__all__ = [
    "EvaluationResult",
    "IngredientFinding",
    "DimensionSummary",
    "ScanResultResponse",
]
