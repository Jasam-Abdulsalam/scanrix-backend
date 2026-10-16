from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class FavoriteRead(BaseModel):
    """A saved product. verdict/overall_score are the product's STORED values (the product screen re-evaluates)."""
    id: str
    barcode: str
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    verdict: Optional[str] = None
    overall_score: Optional[int] = None
    added_at: datetime


class FavoritePage(BaseModel):
    items: List[FavoriteRead]
    next_cursor: Optional[str] = None
    has_more: bool = False


class FavoriteBarcodes(BaseModel):
    barcodes: List[str]
