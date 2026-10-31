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
    """
    Rate limiter dependency: at most SCAN_RATE_LIMIT_PER_MINUTE scans per user per minute.
    Abuse protection only (scanning itself is unlimited). Fixed window: one counter per
    user per clock minute, so a burst across a minute boundary can reach 2x the limit.
    """
    import time
    from app.db.redis import get_redis
    from app.core.config import settings

    if settings.TEST_MODE:
        return current_user

    user_id = str(current_user["_id"])
    now = int(time.time())
    key = f"rate_limit:scans:{user_id}:{now // 60}"

    redis = get_redis()

    try:
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, 60) # the window's key is useless after its minute ends

        if count > settings.SCAN_RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(60 - now % 60)},
                detail={"code": "scan_rate_limited", "message": "Too many scans. Please wait a moment and try again."}
            )
            
    except Exception as e:
        # If redis fails but it's not a 429 exception, we still might want to let them scan 
        # (fail open) rather than blocking legitimate users if the cache server goes down
        if isinstance(e, HTTPException):
            raise e
        print(f"⚠️ Rate limiter cache error: {e}")
        
    return current_user
