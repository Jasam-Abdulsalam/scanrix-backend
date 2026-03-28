from google import genai
from groq import Groq
from app.core.config import settings
from app.db.redis import get_redis
from typing import Optional
import json
import asyncio
import time
import hashlib
from collections import deque

class AIService:
    def __init__(self):
        """Initialize both AI clients"""
        self.gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.gemini_model = 'gemini-2.5-flash'
        
        # Groq client
        self.groq_client = Groq(api_key=settings.GROQ_API_KEY)
        self.groq_model = 'llama-3.1-8b-instant' # Extremely fast, free tier
        
        print(f"✅ AI Service initialized with Groq ({self.groq_model}) and Gemini ({self.gemini_model})")
    
    def _generate_cache_key(self, ingredients_text: str, category: str) -> str:
        """Create a unique cache key based on a sorted list of ingredients"""
        normalized = ",".join(sorted([i.strip().lower() for i in ingredients_text.split(",") if i.strip()]))
        key_hash = hashlib.md5(f"{category}:{normalized}".encode()).hexdigest()
        return f"ai_analysis:{key_hash}"

    async def analyze_ingredients(self, ingredients_text: str, category: str = "food") -> Optional[dict]:
        """Analyze ingredients using Groq -> Gemini -> Fallback waterfall"""
        
        # 1. Check Redis Cache First
        cache_key = self._generate_cache_key(ingredients_text, category)
        redis = get_redis()
        try:
            cached_data = redis.get(cache_key)
            if cached_data:
                print(f"⚡ REDIS CACHE HIT ({cache_key})! Returning instantly.")
                if isinstance(cached_data, str):
                    return json.loads(cached_data)
                return cached_data
        except Exception as e:
            print(f"⚠️ Redis cache read error (ignoring): {e}")

        prompt = self._create_analysis_prompt(ingredients_text, category)
        parsed = None
        loop = asyncio.get_event_loop()

        # 2. Try Groq (Primary, Fast)
        try:
            print("🧠 Attempting analysis with Groq (Primary)...")
            # Groq requires 'your-groq-api-key-here' to be valid, otherwise it throws an auth error.
            if settings.GROQ_API_KEY and settings.GROQ_API_KEY != "your-groq-api-key-here":
                response_text = await loop.run_in_executor(None, self._generate_with_groq_sync, prompt)
                parsed = self._parse_json_response(response_text)
                if parsed:
                    print("✅ Groq analysis successful")
            else:
                print("⚠️ Groq API key not set properly. Skipping to Gemini.")
        except Exception as e:
            print(f"⚠️ Groq API failed ({e}). Falling back to Gemini...")

        # 3. Try Gemini (Fallback)
        if not parsed:
            try:
                print("🧠 Attempting analysis with Gemini (Fallback)...")
                response_text = await loop.run_in_executor(None, self._generate_with_gemini_sync, prompt)
                parsed = self._parse_json_response(response_text)
                if parsed:
                    print("✅ Gemini analysis successful")
            except Exception as e:
                print(f"❌ Gemini API failed ({e}). Using static fallback...")

        # 4. Final Fallback (If both AI fail)
        if not parsed:
            parsed = self._get_fallback_analysis(ingredients_text, category)

        # Save to Redis Cache (Cache for 30 days = 2592000 seconds)
        try:
            redis.setex(cache_key, 2592000, json.dumps(parsed))
            print(f"💾 Saved analysis to Redis Cache ({cache_key})")
        except Exception as e:
            print(f"⚠️ Redis cache write error: {e}")
            
        return parsed
    
    def _generate_with_groq_sync(self, prompt: str):
        """Synchronous call to Groq"""
        completion = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=[
                {"role": "system", "content": "You are an API that only returns valid JSON without markdown wrapping."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        return completion.choices[0].message.content

    def _generate_with_gemini_sync(self, prompt: str):
        """Synchronous call to Gemini"""
        response = self.gemini_client.models.generate_content(
            model=self.gemini_model,
            contents=prompt
        )
        return response.text
    
    def _create_analysis_prompt(self, ingredients: str, category: str) -> str:
        """Create prompt for AI"""
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
    
    def _parse_json_response(self, response_text: str) -> Optional[dict]:
        """Parse AI response to structured data"""
        if not response_text:
             return None
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
            
            # Validate structure
            required_fields = ["overall_score", "verdict", "ingredients"]
            if not all(field in data for field in required_fields):
                print(f"⚠️  AI response missing required fields")
                return None
            
            return data
        
        except json.JSONDecodeError as e:
            print(f"Failed to parse AI response: {e}")
            print(f"Response was: {response_text[:200]}...")
            return None
    
    def _get_fallback_analysis(self, ingredients_text: str, category: str) -> dict:
        """Return basic analysis if AI fails"""
        print("⚠️  Using fallback analysis")
        ingredients_list = [ing.strip() for ing in ingredients_text.split(",")[:10]]
        score = 60
        concerns = []
        text_lower = ingredients_text.lower()
        if any(word in text_lower for word in ["artificial", "color", "dye"]):
            score -= 10
            concerns.append("Contains artificial ingredients")
        if any(word in text_lower for word in ["high fructose", "corn syrup"]):
            score -= 15
            concerns.append("Contains high fructose corn syrup")
        if "trans fat" in text_lower or "hydrogenated" in text_lower:
            score -= 20
            concerns.append("Contains trans fats")
        if "organic" in text_lower:
            score += 10
        if "natural" in text_lower:
            score += 5
        score = max(10, min(100, score))
        if score >= 70: verdict = "safe"
        elif score >= 40: verdict = "caution"
        else: verdict = "avoid"
        return {
            "overall_score": score,
            "verdict": verdict,
            "ingredients": [
                {
                    "name": ing,
                    "purpose": "Common ingredient",
                    "safety_rating": score,
                    "concerns": concerns if concerns else ["Basic analysis - AI unavailable"],
                    "is_natural": "natural" in text_lower or "organic" in text_lower
                }
                for ing in ingredients_list
            ],
            "summary": f"Basic {category} analysis: {len(ingredients_list)} ingredients. " + 
                      (concerns[0] if concerns else "AI analysis temporarily unavailable.")
        }

ai_service = AIService()
