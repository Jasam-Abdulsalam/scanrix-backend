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

    # Opt-in "Get AI verdict" (POST /api/v1/ai/analyze-product). Results never overwrite the
    # database verdict. Credits are per user per ISO week (UTC) and shared with future AI features.
    AI_CREDITS_PER_WEEK: int = 6
    AI_ANALYSIS_TTL_DAYS: int = 90            # cached AI analyses expire after this (invalidation)
    AI_ANALYSIS_TIMEOUT_SECONDS: float = 30.0  # per AI provider call

    # Saved products: soft cap per user (checked before insert, so two simultaneous adds may overshoot by 1)
    FAVORITES_MAX_PER_USER: int = 500

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