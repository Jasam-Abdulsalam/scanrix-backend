"""Copy a product's photo to our Cloudinary once, so the app loads it from Cloudinary's CDN instead of
Open Food Facts / Open Beauty Facts, whose image servers are often slow (seconds, sometimes 15 s+).

Runs after the scan has answered (a background task), never in the request: the first scan still
shows the original URL; every later read gets the copy. Best effort: no Cloudinary keys, a failed
download or upload all just leave the original URL in place. The original is kept in
`image_source_url`.
"""
import asyncio
import logging
import re
from typing import Optional

import cloudinary
import cloudinary.exceptions
import cloudinary.uploader
import urllib3.exceptions

from app.core.config import settings
from app.crud import crud_product

logger = logging.getLogger(__name__)

FOLDER = "product_images"

# What a failed copy can raise: Cloudinary refusing the source, the HTTP call failing, the timeout.
_COPY_ERRORS = (
    cloudinary.exceptions.Error,
    urllib3.exceptions.HTTPError,
    OSError,
    asyncio.TimeoutError,
    KeyError,  # a response without secure_url
)


def is_configured() -> bool:
    return bool(settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET)


def is_mirrored(url: Optional[str]) -> bool:
    return bool(url) and "res.cloudinary.com/" in url


def needs_mirror(url: Optional[str]) -> bool:
    """An https photo that isn't on Cloudinary yet (http is skipped: iOS blocks it anyway)."""
    return bool(url) and url.startswith("https://") and not is_mirrored(url)


def public_id_for(barcode: str) -> str:
    """Cloudinary public id from the barcode (only safe characters)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", barcode)[:100] or "unknown"


def _upload(source_url: str, barcode: str) -> str:
    """Blocking (Cloudinary's SDK is sync): call through run_in_executor."""
    side = settings.PRODUCT_IMAGE_MIRROR_MAX_SIDE
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    # Cloudinary downloads the remote URL itself. Overwrite: a re-run replaces a stale copy.
    result = cloudinary.uploader.upload(
        source_url,
        folder=FOLDER,
        public_id=public_id_for(barcode),
        overwrite=True,
        resource_type="image",
        format="jpg",
        transformation=[{"width": side, "height": side, "crop": "limit"}],
        timeout=settings.PRODUCT_IMAGE_MIRROR_TIMEOUT_SECONDS,
    )
    return result["secure_url"]


async def mirror_product_image(barcode: str, source_url: Optional[str]) -> Optional[str]:
    """Copies the photo and saves the new URL on the product. Returns it, or None when skipped/failed."""
    if not (is_configured() and needs_mirror(source_url)):
        return None
    try:
        url = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(None, _upload, source_url, barcode),
            timeout=settings.PRODUCT_IMAGE_MIRROR_TIMEOUT_SECONDS + 5,
        )
    except _COPY_ERRORS as e:  # best effort (fail-open): the original URL stays
        logger.warning("Product image mirror failed for %s: %s", barcode, e)
        return None
    # Only replaces the URL we copied: if the product's photo changed meanwhile, leave it alone.
    saved = await crud_product.set_mirrored_image(barcode, source_url, url)
    return url if saved else None
