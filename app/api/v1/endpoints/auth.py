from fastapi import APIRouter, Depends, HTTPException, status
from datetime import timedelta
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from app.schemas.user import UserCreate, UserLogin, UserResponse, GoogleLoginRequest, UserProfileUpdate
from app.schemas.token import Token
from app.crud.crud_user import create_user, get_user_by_email, create_google_user, update_user_profile
from app.core.security import verify_password, create_access_token
from app.core.config import settings
from app.core.exceptions import ConflictException, UnauthorizedException, RequestTimeoutException, InternalServerException, NotFoundException
from app.models.users import user_helper
from app.api.deps import get_current_user
import asyncio

import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    try:
        existing_user = await asyncio.wait_for(get_user_by_email(user.email), timeout=10.0)
        if existing_user:
            raise ConflictException(detail="Email already registered")

        new_user = await asyncio.wait_for(create_user(user), timeout=30.0)
        return user_helper(new_user)

    except (ConflictException, RequestTimeoutException):
        raise
    except asyncio.TimeoutError:
        raise RequestTimeoutException()
    except Exception as e:
        logger.exception(f"Registration error: {e}")
        raise InternalServerException()

@router.post("/login", response_model=Token)
async def login(user_login: UserLogin):
    try:
        user = await asyncio.wait_for(get_user_by_email(user_login.email), timeout=5.0)
        if not user:
            raise UnauthorizedException(detail="Incorrect email or password")

        if not verify_password(user_login.password, user["hashed_password"]):
            raise UnauthorizedException(detail="Incorrect email or password")

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["email"]},
            expires_delta=access_token_expires
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "profile_completed": user.get("profile_completed", True),
        }

    except (UnauthorizedException, RequestTimeoutException):
        raise
    except asyncio.TimeoutError:
        raise RequestTimeoutException()
    except Exception as e:
        logger.exception(f"Login error: {e}")
        raise InternalServerException()

@router.post("/google", response_model=Token)
async def google_login(payload: GoogleLoginRequest):
    if not settings.GOOGLE_CLIENT_ID:
        logger.error("Google sign-in attempt failed: GOOGLE_CLIENT_ID is not configured in backend .env")
        raise InternalServerException(detail="Google sign-in is not configured on the server. Please set GOOGLE_CLIENT_ID in .env.")

    try:
        # verify_oauth2_token is a blocking SDK call (fetches Google's public
        # certs on first use) — run it off the event loop, same as the sync
        # LLM calls in app/services/ai_service.py.
        idinfo = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: google_id_token.verify_oauth2_token(
                payload.id_token,
                google_requests.Request(),
                audience=settings.GOOGLE_CLIENT_ID,
            ),
        )
    except ValueError as e:
        logger.warning(f"Google token verification failed (invalid token or audience mismatch): {e}")
        raise UnauthorizedException(detail=f"Invalid Google ID token: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error during Google token verification: {e}")
        raise InternalServerException(detail="Failed to verify Google ID token")

    email = idinfo.get("email")
    if not email or not idinfo.get("email_verified"):
        raise UnauthorizedException(detail="Google account email not verified")

    try:
        user = await asyncio.wait_for(get_user_by_email(email), timeout=5.0)
        is_new_user = False
        if not user:
            name = idinfo.get("name") or email.split("@")[0]
            user = await asyncio.wait_for(
                create_google_user(email=email, name=name, google_id=idinfo["sub"]),
                timeout=30.0,
            )
            is_new_user = True
    except RequestTimeoutException:
        raise
    except asyncio.TimeoutError:
        raise RequestTimeoutException()
    except Exception as e:
        logger.exception(f"Google user lookup/creation error: {e}")
        raise InternalServerException()

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "is_new_user": is_new_user,
        "profile_completed": user.get("profile_completed", True),
    }


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return user_helper(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserProfileUpdate,
    current_user: dict = Depends(get_current_user),
):
    try:
        updated_user = await asyncio.wait_for(
            update_user_profile(
                user_id=str(current_user["_id"]),
                name=payload.name,
                photo_url=payload.photo_url,
            ),
            timeout=10.0,
        )
        if updated_user is None:
            raise NotFoundException(detail="User not found")
        return user_helper(updated_user)

    except (NotFoundException, RequestTimeoutException):
        raise
    except asyncio.TimeoutError:
        raise RequestTimeoutException()
    except Exception as e:
        logger.exception(f"Profile update error: {e}")
        raise InternalServerException()
