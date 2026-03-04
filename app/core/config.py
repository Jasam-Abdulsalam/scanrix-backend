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
    
    # Firebase (optional)
    FIREBASE_PROJECT_ID: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()