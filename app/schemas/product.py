from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class Ingredient(BaseModel):
    name: str
    purpose: Optional[str] = None
    safety_rating: int = Field(ge=0, le=100)
    concerns: List[str] = []
    is_natural: bool = False

class ProductBase(BaseModel):
    barcode: str
    name: str
    brand: str
    category: str  # "food" | "cosmetic" | "household"

class ProductCreate(ProductBase):
    ingredients: List[Ingredient]
    overall_score: int = Field(ge=0, le=100)
    verdict: str  # "safe" | "caution" | "avoid"

class ProductResponse(ProductBase):
    id: str
    ingredients: List[Ingredient]
    overall_score: int
    verdict: str
    image_url: Optional[str] = None
    source: str  # "openfoodfacts" | "gemini" | "manual"
    created_at: datetime
    
    class Config:
        from_attributes = True

class ScanRequest(BaseModel):
    barcode: Optional[str] = None
    image_base64: Optional[str] = None

class ScanResponse(BaseModel):
    product: ProductResponse
    personalized_score: Optional[int] = None
    concerns_for_user: List[str] = []