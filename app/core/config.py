from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Scanrix API"
    DEBUG: bool = True
    # Testing only: when True, the daily scan limit is skipped. Never enable in production.
    TEST_MODE: bool = False
    
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
    GROQ_MODEL: str = "openai/gpt-oss-20b"    # Groq retires models; check console.groq.com/docs/models
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GROQ_MAX_OUTPUT_TOKENS: int = 2048        # reasoning models count their thinking here too; 1024 truncated answers
    AI_CREDITS_PER_WEEK: int = 6
    AI_ANALYSIS_TTL_DAYS: int = 90            # cached AI analyses expire after this (invalidation)
    AI_ANALYSIS_TIMEOUT_SECONDS: float = 30.0  # per AI provider call
    AI_ALTERNATIVES_TTL_DAYS: int = 30        # cached AI alternatives expire after this (prices go stale)

    # Product photos for AI alternatives (app/services/product_image_service.py). SEARXNG_URL is our
    # private SearXNG (docker-compose sets it); empty = only Open Food/Beauty Facts photos.
    SEARXNG_URL: Optional[str] = None
    PRODUCT_IMAGE_TIMEOUT_SECONDS: float = 6.0      # per image source call
    PRODUCT_IMAGES_TOTAL_SECONDS: float = 15.0      # all images for one answer; slower = no images

    # Scan endpoints: abuse protection only, normal use never reaches it (scanning is unlimited)
    SCAN_RATE_LIMIT_PER_MINUTE: int = 30

    # Saved products: soft cap per user (checked before insert, so two simultaneous adds may overshoot by 1)
    FAVORITES_MAX_PER_USER: int = 500

    # Firebase (optional)
    FIREBASE_PROJECT_ID: Optional[str] = None

    # Google Sign-In: OAuth web client ID, used as the `audience` when verifying
    # ID tokens the Flutter app sends to POST /auth/google. Must match the
    # Web client ID configured in Google Cloud Console (see scanrix-frontend's
    # CLAUDE.md "Google Sign-In" section for the client setup).
    GOOGLE_CLIENT_ID: Optional[str] = None

    # Extra OAuth client IDs (comma-separated) whose Google ID tokens are also
    # accepted. Needed for iOS: Google puts the *iOS* client ID in the token's
    # `aud` claim there (Android uses the web client ID), so the iOS client ID
    # goes here. Only list clients from your own Google Cloud project.
    # Empty = only GOOGLE_CLIENT_ID is accepted.
    GOOGLE_EXTRA_CLIENT_IDS: str = ""

    @property
    def google_audiences(self) -> list[str]:
        """Every client ID a Google ID token may be issued for: GOOGLE_CLIENT_ID
        first, then GOOGLE_EXTRA_CLIENT_IDS. Blanks and duplicates are dropped."""
        ids = [self.GOOGLE_CLIENT_ID or "", *self.GOOGLE_EXTRA_CLIENT_IDS.split(",")]
        return list(dict.fromkeys(i.strip() for i in ids if i.strip()))

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