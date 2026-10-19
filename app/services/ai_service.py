from google import genai
from groq import Groq
from app.core.config import settings

class AIService:
    """Holds the Groq and Gemini clients; ai_product_service / ai_fallback_service call the *_sync generators."""
    def __init__(self):
        """Initialize both AI clients"""
        self.gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.gemini_model = 'gemini-3.6-flash'
        
        # Groq client
        self.groq_client = Groq(api_key=settings.GROQ_API_KEY)
        self.groq_model = 'llama-3.1-8b-instant' # Extremely fast, free tier
        
        print(f"✅ AI Service initialized with Groq ({self.groq_model}) and Gemini ({self.gemini_model})")
    
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

ai_service = AIService()
