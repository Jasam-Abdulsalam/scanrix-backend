import asyncio
import traceback
import requests
from typing import Optional

class OpenFoodFactsService:
    BASE_URL = "https://world.openfoodfacts.org/api/v2"

    def _fetch_product_sync(self, barcode: str) -> Optional[dict]:
        """Synchronous fetch — runs in a thread pool to avoid blocking the event loop."""
        response = requests.get(
            f"{self.BASE_URL}/product/{barcode}",
            headers={"User-Agent": "Scanrix - Health Scanner App"},
            timeout=30,
        )
        print("STATUS CODE:", response.status_code)

        if response.status_code != 200:
            print(f"Open Food Facts returned non-200: {response.status_code}")
            print("Response body:", response.text[:500])
            return None

        data = response.json()
        print("JSON STATUS FIELD:", data.get("status"))

        # v2 API returns status as "success" or "failure" (string)
        # v0/v1 returned 1 or 0 (int) — handle both for safety
        status = data.get("status")
        if status == "success" or status == 1:
            product = data.get("product", {})
            return self._parse_product(product, barcode)

        print("Product not found in Open Food Facts. status =", status)
        return None

    async def get_product(self, barcode: str) -> Optional[dict]:
        """Get product from Open Food Facts API (async wrapper)."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._fetch_product_sync, barcode)
        except Exception as e:
            print(f"Error fetching from Open Food Facts: {type(e).__name__}: {e}")
            traceback.print_exc()
            return None
    
    def _parse_product(self, product: dict, barcode: str) -> dict:
        """Parse Open Food Facts response to our format"""
        return {
            "barcode": barcode,
            "name": product.get("product_name", "Unknown Product"),
            "brand": product.get("brands", "Unknown Brand"),
            "category": self._determine_category(product),
            "image_url": product.get("image_url"),
            "ingredients": self._parse_ingredients(product.get("ingredients", [])),
            "overall_score": self._calculate_score(product),
            "verdict": "unknown",
            "source": "openfoodfacts"
        }
    
    def _determine_category(self, product: dict) -> str:
        """Determine if product is food, cosmetic, etc."""
        categories = product.get("categories", "").lower()
        if any(word in categories for word in ["cosmetic", "beauty", "skincare"]):
            return "cosmetic"
        return "food"
    
    def _parse_ingredients(self, ingredients: list) -> list:
        """Parse ingredients list"""
        parsed = []
        for ing in ingredients[:10]:  # Limit to first 10
            parsed.append({
                "name": ing.get("text", "Unknown"),
                "purpose": None,
                "safety_rating": 50,  # Default neutral
                "concerns": [],
                "is_natural": ing.get("vegan") == "yes"
            })
        return parsed
    
    def _calculate_score(self, product: dict) -> int:
        """Calculate basic score from Nutri-Score or ingredients"""
        nutriscore = product.get("nutriscore_grade", "").upper()
        score_map = {"A": 90, "B": 75, "C": 60, "D": 45, "E": 30}
        return score_map.get(nutriscore, 50)

openfoodfacts_service = OpenFoodFactsService()