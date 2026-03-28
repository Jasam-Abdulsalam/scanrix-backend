from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import decode_access_token
from app.crud.crud_user import get_user_by_email

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Dependency to get current authenticated user"""
    token = credentials.credentials
    
    # Decode token
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    
    # Get user from database
    user = await get_user_by_email(email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user

async def check_rate_limit(current_user: dict = Depends(get_current_user)):
    """Rate limiter dependency: 10 scans per user per day"""
    import datetime
    from app.db.redis import get_redis
    
    user_id = str(current_user["_id"])
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    key = f"rate_limit:scans:{user_id}:{today}"
    
    redis = get_redis()
    
    try:
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, 86400) # Expire in 24 hours
            
        if count > 10:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Daily scan limit (10) reached. Please try again tomorrow."
            )
            
    except Exception as e:
        # If redis fails but it's not a 429 exception, we still might want to let them scan 
        # (fail open) rather than blocking legitimate users if the cache server goes down
        if isinstance(e, HTTPException):
            raise e
        print(f"⚠️ Rate limiter cache error: {e}")
        
    return current_user