"""Cursor pagination helpers (API_CONTRACT.md section 5).

Lists are ordered newest first by (sort field desc, _id desc). The `_id` tie-break makes the order
total, so two rows with the same timestamp are never skipped or repeated between pages. The cursor
is the last row's (sort value, _id), base64url JSON: opaque to clients, not signed (a tampered
cursor can only move the caller around their OWN rows, every query also filters by user_id).

Cost per page: O(limit) with an index on (user_id, <field> desc, _id desc), no skip().
"""
import base64
import binascii
import json
from datetime import datetime
from typing import List, Optional, Tuple

from bson import ObjectId
from bson.errors import InvalidId

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class InvalidCursor(Exception):
    """The cursor is not one this server produced."""


def encode_cursor(sort_value: datetime, doc_id: ObjectId) -> str:
    raw = json.dumps({"t": sort_value.isoformat(), "i": str(doc_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> Tuple[datetime, ObjectId]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        return datetime.fromisoformat(data["t"]), ObjectId(data["i"])
    except (ValueError, KeyError, TypeError, InvalidId, binascii.Error) as e:
        raise InvalidCursor() from e


def after_cursor_filter(field: str, cursor: Optional[str]) -> dict:
    """Mongo filter for 'rows strictly after the cursor' in (field desc, _id desc) order."""
    if cursor is None:
        return {}
    value, doc_id = decode_cursor(cursor)
    return {"$or": [{field: {"$lt": value}}, {field: value, "_id": {"$lt": doc_id}}]}



def newest_first(field: str) -> list:
    return [(field, -1), ("_id", -1)]


def split_page(docs: List[dict], limit: int, field: str) -> Tuple[List[dict], Optional[str]]:
    """`docs` were fetched with limit + 1: the extra row only tells us whether a next page exists."""
    if len(docs) <= limit:
        return docs, None
    page = docs[:limit]
    return page, encode_cursor(page[-1][field], page[-1]["_id"])
