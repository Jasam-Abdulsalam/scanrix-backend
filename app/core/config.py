from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Scanrix API"
    DEBUG: bool = True
    
    # MongoDB
    MONGODB_URL: str
    DATABASE_NAME: str = "SCANRIX"

    
    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Gemini API
    GEMINI_API_KEY: str
    
    # Groq API
    GROQ_API_KEY: str = "your-groq-api-key-here"

    # Ingredient engine: when False, unknown ingredients stay "not assessed" and
    # no AI call or DB write happens for them. Turn on only once AI keys are set.
    AI_FALLBACK_ENABLED: bool = False

    # Opt-in "Analyze with AI" button (POST /api/v1/ai/explain-ingredients). The user taps it,
    # results are cached per ingredient and never change a verdict.
    AI_EXPLAIN_DAILY_LIMIT: int = 5           # requests per user per UTC day
    AI_EXPLAIN_TIMEOUT_SECONDS: float = 25.0  # per AI provider call
    
    # Firebase (optional)
    FIREBASE_PROJECT_ID: Optional[str] = None

    # Google Sign-In: OAuth web client ID, used as the `audience` when verifying
    # ID tokens the Flutter app sends to POST /auth/google. Must match the
    # Web client ID configured in Google Cloud Console (see scanrix-frontend's
    # CLAUDE.md "Google Sign-In" section for the client setup).
    GOOGLE_CLIENT_ID: Optional[str] = None

    # Cloudinary: used by POST /auth/me/photo to store profile photos.
    # Get these from your Cloudinary dashboard (cloudinary.com/console).
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None

    # Upstash Redis
    UPSTASH_REDIS_REST_URL: str
    UPSTASH_REDIS_REST_TOKEN: str
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()