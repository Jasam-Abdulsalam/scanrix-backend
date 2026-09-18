from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class GoogleLoginRequest(BaseModel):
    id_token: str

class UserResponse(UserBase):
    id: str
    name: str
    created_at: datetime
    photo_url: Optional[str] = None
    profile_completed: bool = True

    class Config:
        from_attributes = True

class UserProfileUpdate(BaseModel):
    name: str = Field(..., min_length=1)
    photo_url: Optional[str] = None

class UserInDB(UserBase):
    id: str
    name: str
    hashed_password: str
    created_at: datetime
    preferences: Optional[dict] = None