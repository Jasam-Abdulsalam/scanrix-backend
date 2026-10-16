from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HistoryProduct(BaseModel):
    """The few product fields a history row needs to draw itself and open the product."""
    barcode: str
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None


class HistoryRead(BaseModel):
    """One scan-history entry. `product` is null when the product no longer exists."""
    id: str
    user_id: str
    product_id: str
    verdict: Optional[str] = None
    personalized_score: Optional[int] = None
    scanned_at: datetime
    product: Optional[HistoryProduct] = None
