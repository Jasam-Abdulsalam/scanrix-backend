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
    
    # Firebase (optional)
    FIREBASE_PROJECT_ID: Optional[str] = None

    # Google Sign-In: OAuth web client ID, used as the `audience` when verifying
    # ID tokens the Flutter app sends to POST /auth/google. Must match the
    # Web client ID configured in Google Cloud Console (see scanrix-frontend's
    # CLAUDE.md "Google Sign-In" section for the client setup).
    GOOGLE_CLIENT_ID: Optional[str] = None
    
    # Upstash Redis
    UPSTASH_REDIS_REST_URL: str
    UPSTASH_REDIS_REST_TOKEN: str
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()