"""Find a photo for a product we only know by name (AI alternatives have no barcode).

1. Open Food Facts / Open Beauty Facts search: free and openly licensed.
2. Our private SearXNG (settings.SEARXNG_URL): free, but it reads public search engines'
   results, so it can be rate-limited or blocked; used only when (1) finds nothing.

Best effort: every failure (timeout, block, no match) just means "no image" (None), never an
error. A result is only accepted when its title matches the brand AND part of the name, so a
listicle or a different product isn't shown as this one. https only (iOS blocks http images).
"""
import asyncio
import logging
import re
from typing import Iterable, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

USER_AGENT = "Scanrix/1.0 (product images for AI alternatives)"
MAX_URL_CHARS = 1000
MIN_NAME_OVERLAP = 0.5  # share of the product name's words that must appear in the title
SKIP_HOSTS = ("pinimg.com",)  # Pinterest images are mostly collages/listicles, rarely the pack


def _words(text: str) -> set:
    return {w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(w) > 1}


def title_matches(title: str, name: str, brand: str) -> bool:
    """Brand present and at least MIN_NAME_OVERLAP of the name's words present (pure, testable)."""
    t, b, n = _words(title), _words(brand), _words(name) - _words(brand)
    if not b or not b <= t:
        return False
    return not n or len(n & t) / len(n) >= MIN_NAME_OVERLAP


def usable_url(url: Optional[str]) -> Optional[str]:
    if not url or not url.startswith("https://") or len(url) > MAX_URL_CHARS:
        return None
    return None if any(h in url for h in SKIP_HOSTS) else url


def best_searxng_image(results: Iterable[dict], name: str, brand: str) -> Optional[str]:
    """First result whose title matches the product, in SearXNG's ranking order."""
    for r in results:
        url = usable_url(r.get("img_src"))
        if url and title_matches(r.get("title", ""), name, brand):
            return url
    return None


def _get_json(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT},
                     timeout=settings.PRODUCT_IMAGE_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


def _from_open_facts(name: str, brand: str, cosmetic: bool) -> Optional[str]:
    host = "world.openbeautyfacts.org" if cosmetic else "world.openfoodfacts.org"
    data = _get_json(f"https://{host}/cgi/search.pl",
                     {"search_terms": f"{brand} {name}", "search_simple": 1, "json": 1, "page_size": 5})
    for p in data.get("products", []):
        title = f"{p.get('brands', '')} {p.get('product_name', '')}"
        url = usable_url(p.get("image_front_url") or p.get("image_url"))
        if url and title_matches(title, name, brand):
            return url
    return None


def _from_searxng(name: str, brand: str, size: Optional[str]) -> Optional[str]:
    query = " ".join(x for x in (brand, name, size) if x)
    data = _get_json(f"{settings.SEARXNG_URL.rstrip('/')}/search",
                     {"q": query, "categories": "images", "format": "json", "safesearch": 1})
    return best_searxng_image(data.get("results", []), name, brand)


async def find_image(name: str, brand: str, size: Optional[str] = None, cosmetic: bool = True) -> Optional[str]:
    """A photo URL for this product, or None. Never raises."""
    sources = [lambda: _from_open_facts(name, brand, cosmetic)]
    if settings.SEARXNG_URL:
        sources.append(lambda: _from_searxng(name, brand, size))
    for source in sources:
        try:
            url = await asyncio.to_thread(source)
            if url:
                return url
        except Exception as e:  # noqa: BLE001 - best effort: any failure just means "try the next source"
            logger.info("Product image lookup failed (%s) for %r", type(e).__name__, f"{brand} {name}"[:80])
    return None
