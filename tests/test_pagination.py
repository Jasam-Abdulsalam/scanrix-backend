from datetime import datetime

from bson import ObjectId

from app.core.pagination import (
    InvalidCursor, after_cursor_filter, decode_cursor, encode_cursor, split_page,
)


def _raises_invalid(cursor):
    try:
        decode_cursor(cursor)
    except InvalidCursor:
        return True
    return False


def test_cursor_round_trips_exactly():
    t, oid = datetime(2026, 10, 16, 8, 41, 5, 123000), ObjectId()
    assert decode_cursor(encode_cursor(t, oid)) == (t, oid)


def test_garbage_cursors_are_rejected_not_crashes():
    for bad in ["", "not-base64!!", "e30", "bm90LWpzb24", encode_cursor(datetime(2026, 1, 1), ObjectId())[:-6]]:
        assert _raises_invalid(bad), bad
    # valid base64 JSON but wrong shape / values
    import base64, json
    for payload in [{"t": "nope", "i": "x"}, {"t": "2026-01-01T00:00:00"}, [1, 2], {"t": "2026-01-01T00:00:00", "i": "zz"}]:
        token = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        assert _raises_invalid(token), payload


def test_filter_is_empty_without_a_cursor_and_strictly_after_with_one():
    assert after_cursor_filter("scanned_at", None) == {}
    t, oid = datetime(2026, 10, 16), ObjectId()
    f = after_cursor_filter("scanned_at", encode_cursor(t, oid))
    assert f == {"$or": [{"scanned_at": {"$lt": t}}, {"scanned_at": t, "_id": {"$lt": oid}}]}


def test_split_page_only_issues_a_cursor_when_there_is_more():
    docs = [{"_id": ObjectId(), "t": datetime(2026, 1, i)} for i in range(1, 4)]
    page, nxt = split_page(docs[:3], 3, "t")          # exactly a full page, nothing beyond
    assert len(page) == 3 and nxt is None
    page, nxt = split_page(docs, 2, "t")              # one extra row fetched -> more exists
    assert len(page) == 2 and nxt is not None
    assert decode_cursor(nxt) == (docs[1]["t"], docs[1]["_id"])   # points at the LAST row of the page
    assert split_page([], 5, "t") == ([], None)
