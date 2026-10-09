from fastapi import FastAPI
from pydantic import BaseModel, EmailStr, Field

app = FastAPI()

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: str

@app.post("/register")
def register(user_in: UserCreate):
    return {"email": user_in.email, "name": user_in.name}