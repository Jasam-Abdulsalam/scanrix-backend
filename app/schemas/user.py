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

class UserResponse(UserBase):
    id: str
    name: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserInDB(UserBase):
    id: str
    name: str
    hashed_password: str
    created_at: datetime
    preferences: Optional[dict] = None