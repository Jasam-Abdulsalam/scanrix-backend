from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_new_user: bool | None = None
    profile_completed: bool | None = None

class TokenData(BaseModel):
    email: str | None = None