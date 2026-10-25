from pydantic import BaseModel, EmailStr, Field, StringConstraints
from typing import Annotated, Optional
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
    # False: an unknown email gets 404 `account_not_found` instead of a new account, and the
    # app creates it later with POST /auth/google/signup. Default True keeps old app versions working.
    create_if_missing: bool = True

class GoogleSignupRequest(BaseModel):
    id_token: str
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    photo_url: Optional[str] = Field(None, max_length=2048)

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