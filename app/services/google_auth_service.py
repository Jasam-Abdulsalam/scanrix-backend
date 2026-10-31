"""
Google Sign-In: ID-token verification and account creation.

Sign-up is a two-step flow (API_CONTRACT.md section 3): POST /auth/google with
create_if_missing=false only logs in existing accounts, and POST /auth/google/signup creates
the account once the user confirms their profile. Picking the wrong Google account and
going back therefore leaves nothing in the database.
"""
import asyncio
import logging
from typing import Optional, Tuple

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings
from app.core.exceptions import InternalServerException, UnauthorizedException
from app.crud.crud_user import create_google_user, get_user_by_email

logger = logging.getLogger(__name__)


async def verify_google_id_token(token: str) -> dict:
    """Google's claims for a valid token with a verified email. 401 otherwise."""
    if not settings.GOOGLE_CLIENT_ID:
        logger.error("Google sign-in attempt failed: GOOGLE_CLIENT_ID is not configured in backend .env")
        raise InternalServerException(detail="Google sign-in is not configured on the server. Please set GOOGLE_CLIENT_ID in .env.")

    try:
        # verify_oauth2_token is a blocking SDK call (fetches Google's public certs on first use),
        # so it runs off the event loop.
        idinfo = await asyncio.get_running_loop().run_in_executor(
            None,
            # Accept the web client and any extra clients (iOS issues tokens for its own client ID).
            lambda: google_id_token.verify_oauth2_token(
                token, google_requests.Request(), audience=settings.google_audiences,
            ),
        )
    except ValueError as e:
        logger.warning(f"Google token verification failed (invalid token or audience mismatch): {e}")
        raise UnauthorizedException(detail=f"Invalid Google ID token: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error during Google token verification: {e}")
        raise InternalServerException(detail="Failed to verify Google ID token")

    if not idinfo.get("email") or not idinfo.get("email_verified"):
        raise UnauthorizedException(detail="Google account email not verified")
    return idinfo


async def sign_up(idinfo: dict, name: str, photo_url: Optional[str]) -> Tuple[dict, bool]:
    """(user, created). An existing account is returned unchanged, so a retried sign-up
    (lost response, double tap) logs in instead of failing or overwriting the profile."""
    user = await asyncio.wait_for(get_user_by_email(idinfo["email"]), timeout=5.0)
    if user:
        return user, False
    user = await asyncio.wait_for(
        create_google_user(email=idinfo["email"], name=name, google_id=idinfo["sub"],
                           photo_url=photo_url, profile_completed=True),
        timeout=30.0,
    )
    return user, True
