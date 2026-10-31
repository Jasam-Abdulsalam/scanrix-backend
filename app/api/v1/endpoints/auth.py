import cloudinary
import cloudinary.uploader
import cloudinary.exceptions
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from datetime import timedelta
from app.schemas.user import UserCreate, UserLogin, UserResponse, GoogleLoginRequest, GoogleSignupRequest, UserProfileUpdate
from app.schemas.token import Token
from app.crud.crud_user import create_user, get_user_by_email, create_google_user, update_user_profile, delete_user
from app.crud.crud_history import delete_user_history
from app.crud.crud_favorites import delete_user_favorites
from app.core.security import verify_password, create_access_token
from app.core.config import settings
from app.core.exceptions import ConflictException, UnauthorizedException, RequestTimeoutException, InternalServerException, NotFoundException, BadRequestException
from app.models.users import user_helper
from app.api.deps import get_current_user
from app.services import google_auth_service
import asyncio

MAX_PROFILE_PHOTO_SIZE = 5 * 1024 * 1024  # 5MB

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
    """Logs in with a Google ID token. An unknown email creates the account, unless
    create_if_missing is false: then 404 `account_not_found` (sign up with /google/signup)."""
    idinfo = await google_auth_service.verify_google_id_token(payload.id_token)
    email = idinfo["email"]

    try:
        user = await asyncio.wait_for(get_user_by_email(email), timeout=5.0)
        is_new_user = False
        if not user and not payload.create_if_missing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
                "code": "account_not_found", "message": "No Scanrix account uses this Google account yet."})
        if not user:
            name = idinfo.get("name") or email.split("@")[0]
            user = await asyncio.wait_for(
                create_google_user(email=email, name=name, google_id=idinfo["sub"]),
                timeout=30.0,
            )
            is_new_user = True
    except (HTTPException, RequestTimeoutException):
        raise
    except asyncio.TimeoutError:
        raise RequestTimeoutException()
    except Exception as e:
        logger.exception(f"Google user lookup/creation error: {e}")
        raise InternalServerException()

    return _token_response(user, is_new_user)


@router.post("/google/signup", response_model=Token)
async def google_signup(payload: GoogleSignupRequest):
    """Creates the account for a Google ID token with the profile the user confirmed.
    Safe to repeat: an existing account is logged in unchanged (is_new_user=false)."""
    idinfo = await google_auth_service.verify_google_id_token(payload.id_token)
    try:
        user, created = await google_auth_service.sign_up(idinfo, payload.name, payload.photo_url)
    except asyncio.TimeoutError:
        raise RequestTimeoutException()
    except Exception as e:
        logger.exception(f"Google sign-up error: {e}")
        raise InternalServerException()
    return _token_response(user, created)


def _token_response(user: dict, is_new_user: bool) -> dict:
    access_token = create_access_token(
        data={"sub": user["email"]},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
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


@router.post("/me/photo", response_model=UserResponse)
async def upload_profile_photo(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if not (settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET):
        logger.error("Profile photo upload failed: Cloudinary is not configured in backend .env")
        raise InternalServerException(
            detail="Photo uploads are not configured on the server. Please set "
                   "CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in .env."
        )

    if not file.content_type or not file.content_type.startswith("image/"):
        raise BadRequestException(detail="Uploaded file must be an image")

    contents = await file.read()
    if len(contents) > MAX_PROFILE_PHOTO_SIZE:
        raise BadRequestException(detail="Image must be smaller than 5MB")

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
    )

    user_id = str(current_user["_id"])

    try:
        # cloudinary.uploader.upload is a blocking SDK call — run it off the
        # event loop, same pattern as the Google token verification above and
        # the sync LLM calls in app/services/ai_service.py.
        upload_result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: cloudinary.uploader.upload(
                contents,
                folder="profile_photos",
                public_id=user_id,
                overwrite=True,
                invalidate=True,  # bust the CDN cache so a re-upload shows immediately
                resource_type="image",
                format="jpg",
            ),
        )
    except cloudinary.exceptions.Error as e:
        logger.warning(f"Cloudinary rejected profile photo upload: {e}")
        raise BadRequestException(detail="Uploaded file is not a valid image")
    except Exception as e:
        logger.exception(f"Cloudinary upload error: {e}")
        raise InternalServerException()

    photo_url = upload_result["secure_url"]

    try:
        updated_user = await asyncio.wait_for(
            update_user_profile(
                user_id=user_id,
                name=current_user["name"],
                photo_url=photo_url,
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
        logger.exception(f"Profile photo update error: {e}")
        raise InternalServerException()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        # Cascade: scan history and saved products are only ever reachable through the owning
        # account, so it's deleted first, then the account itself.
        await asyncio.wait_for(delete_user_history(user_id), timeout=10.0)
        await asyncio.wait_for(delete_user_favorites(user_id), timeout=10.0)
        await asyncio.wait_for(delete_user(user_id), timeout=10.0)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except RequestTimeoutException:
        raise
    except asyncio.TimeoutError:
        raise RequestTimeoutException()
    except Exception as e:
        logger.exception(f"Account deletion error: {e}")
        raise InternalServerException()