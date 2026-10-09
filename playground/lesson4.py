from typing import Optional
from fastapi import Depends, FastAPI, Header, HTTPException

app = FastAPI()

FAKE_TOKENS = {"token-asha": "Asha", "token-ravi": "Ravi"}

def get_current_user(authorization: Optional[str] = Header(default=None)):
    print("checking token")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    name = FAKE_TOKENS.get(authorization.removeprefix("Bearer "))
    if name is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return name

@app.get("/public")
def public():
    return {"hello": "anyone"}

@app.get("/me")
def me(user: str = Depends(get_current_user)):
    return {"user": user}

@app.get("/history")
def history(user: str = Depends(get_current_user)):
    return {"history_for": user}