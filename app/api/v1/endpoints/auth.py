from fastapi import APIRouter, HTTPException, status
from datetime import timedelta
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.schemas.token import Token
from app.crud.crud_user import create_user, get_user_by_email
from app.core.security import verify_password, create_access_token
from app.core.config import settings
from app.core.exceptions import ConflictException, UnauthorizedException
from app.models.users import user_helper

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    """Register a new user"""
    # Check if user already exists
    existing_user = await get_user_by_email(user.email)
    if existing_user:
        raise ConflictException(detail="Email already registered")
    
    # Create user
    new_user = await create_user(user)
    return user_helper(new_user)

@router.post("/login", response_model=Token)
async def login(user_login: UserLogin):
    """Login user and return access token"""
    # Get user
    user = await get_user_by_email(user_login.email)
    if not user:
        raise UnauthorizedException(detail="Incorrect email or password")
    
    # Verify password
    if not verify_password(user_login.password, user["hashed_password"]):
        raise UnauthorizedException(detail="Incorrect email or password")
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}