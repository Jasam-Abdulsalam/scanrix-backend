import asyncio
import traceback
import requests
from typing import Optional

class OpenBeautyFactsService:
    BASE_URL = "https://world.openbeautyfacts.org/api/v2"

    def _fetch_product_sync(self, barcode: str) -> Optional[dict]:
        """Synchronous fetch — runs in a thread pool to avoid blocking the event loop."""
        try:
            response = requests.get(
                f"{self.BASE_URL}/product/{barcode}",
                headers={"User-Agent": "Scanrix - Health Scanner App"},
                timeout=10,
            )
            if response.status_code != 200:
                print(f"Open Beauty Facts API non-200: {response.status_code}")
                return None

            data = response.json()
            status = data.get("status")
            if status == "success" or status == 1:
                product = data.get("product", {})
                return self._parse_product(product, barcode)
            
            return None
        except Exception as e:
            print(f"Open Beauty request failed: {e}")
            return None

    async def get_product(self, barcode: str) -> Optional[dict]:
        """Get product from Open Beauty Facts API (async wrapper)."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._fetch_product_sync, barcode)
        except Exception as e:
            print(f"Error fetching from Open Beauty Facts: {type(e).__name__}: {e}")
            return None
    
    def _parse_product(self, product: dict, barcode: str) -> dict:
        """Parse Open Beauty Facts response to our format"""
        return {
            "barcode": barcode,
            "name": product.get("product_name", "Unknown Cosmetic"),
            "brand": product.get("brands", "Unknown Brand"),
            "category": "cosmetic",
            "image_url": product.get("image_url"),
            "ingredients": self._parse_ingredients(product.get("ingredients", [])),
            "overall_score": None, # Force background AI analysis
            "verdict": "unknown",
            "source": "openbeautyfacts"
        }
    
    def _parse_ingredients(self, ingredients: list) -> list:
        """Parse ingredients list"""
        parsed = []
        for ing in ingredients[:15]:  # Limit to first 15 for cosmetics
            parsed.append({
                "name": ing.get("text", "Unknown"),
                "purpose": None,
                "safety_rating": 50,  # Default neutral
                "concerns": [],
                "is_natural": False
            })
        return parsed

openbeautyfacts_service = OpenBeautyFactsService()
