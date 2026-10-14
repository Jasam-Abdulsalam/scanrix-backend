from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class Ingredient(BaseModel):
    name: str
    purpose: Optional[str] = None
    safety_rating: Optional[int] = Field(None, ge=0, le=100)
    concerns: List[str] = []
    is_natural: bool = False

class ProductBase(BaseModel):
    barcode: str
    name: str
    brand: str
    category: str  # "food" | "cosmetic" | "household"
    tags: List[str] = []
    quantity: Optional[str] = None

class ProductCreate(ProductBase):
    ingredients: List[Ingredient]
    overall_score: Optional[int] = Field(None, ge=0, le=100)
    verdict: str  # "safe" | "caution" | "avoid" | "analyzing"
    summary: Optional[str] = None

class ProductResponse(ProductBase):
    id: str
    ingredients: List[Ingredient]
    overall_score: Optional[int] = None
    verdict: str
    summary: Optional[str] = None
    image_url: Optional[str] = None
    source: str  # "openfoodfacts" | "gemini" | "manual"
    created_at: datetime

    class Config:
        from_attributes = True

class ScanRequest(BaseModel):
    barcode: Optional[str] = None
    image_base64: Optional[str] = None

from app.services.rule_engine import EvaluationResult

from app.schemas.ai_analysis import AIAnalyzeResponse

class ProductDetailResponse(ProductResponse):
    """GET /products/{barcode}: the product plus a fresh engine evaluation and, if one was already
    generated, the cached AI estimate (both additive fields)."""
    safety_engine: Optional[EvaluationResult] = None
    ai_analysis: Optional[AIAnalyzeResponse] = None

class ScanResponse(BaseModel):
    product: ProductResponse
    personalized_score: Optional[int] = None
    concerns_for_user: List[str] = []
    safety_engine: Optional[EvaluationResult] = None

class AnalyzeTextRequest(BaseModel):
    ingredients_text: str = Field(..., min_length=5, description="Raw ingredients text extracted via OCR")
    category: str = Field("food", description="Product category (food, cosmetic, household)")