import google.generativeai as genai
from app.core.config import settings
from typing import Optional
import json

class GeminiService:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')
    
    async def analyze_ingredients(self, ingredients_text: str, category: str = "food") -> dict:
        """Analyze ingredients using Gemini AI"""
        try:
            prompt = self._create_analysis_prompt(ingredients_text, category)
            response = self.model.generate_content(prompt)
            
            # Parse response
            return self._parse_gemini_response(response.text)
        
        except Exception as e:
            print(f"Gemini API error: {e}")
            return None
    
    def _create_analysis_prompt(self, ingredients: str, category: str) -> str:
        """Create prompt for Gemini"""
        return f"""
Analyze these {category} product ingredients and return ONLY a JSON object (no markdown, no explanation):

Ingredients: {ingredients}

Return this exact JSON structure:
{{
  "overall_score": <number 0-100>,
  "verdict": "<safe|caution|avoid>",
  "ingredients": [
    {{
      "name": "<ingredient name>",
      "purpose": "<what it does>",
      "safety_rating": <0-100>,
      "concerns": ["<concern 1>", "<concern 2>"],
      "is_natural": <true|false>
    }}
  ],
  "summary": "<brief overall assessment in one sentence>"
}}

Make safety_rating:
- 80-100: Safe, no known issues
- 60-79: Generally safe, minor concerns
- 40-59: Caution, some concerns
- 0-39: Avoid, significant concerns

Keep concerns brief and simple. Return ONLY the JSON, nothing else.
"""
    
    def _parse_gemini_response(self, response_text: str) -> dict:
        """Parse Gemini response to structured data"""
        try:
            # Remove markdown code blocks if present
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            
            # Parse JSON
            data = json.loads(cleaned.strip())
            return data
        
        except json.JSONDecodeError as e:
            print(f"Failed to parse Gemini response: {e}")
            print(f"Response was: {response_text}")
            return None

gemini_service = GeminiService()