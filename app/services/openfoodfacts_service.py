import httpx
from typing import Optional

class OpenFoodFactsService:
    BASE_URL = "https://world.openfoodfacts.org/api/v2"
    
    async def get_product(self, barcode: str) -> Optional[dict]:
        """Get product from Open Food Facts API"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/product/{barcode}.json",
                    headers={"User-Agent": "Scanrix - Health Scanner App"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check if product found
                    if data.get("status") == 1:
                        product = data.get("product", {})
                        return self._parse_product(product, barcode)
                    
                return None
        except Exception as e:
            print(f"Error fetching from Open Food Facts: {e}")
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