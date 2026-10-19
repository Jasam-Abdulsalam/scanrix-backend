from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_current_user
from app.schemas.history import HistoryCount, HistoryPage
from app.services import history_service
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, InvalidCursor

router = APIRouter()


@router.get("/", response_model=HistoryPage)
async def get_history(
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: Optional[str] = Query(None, max_length=256),
    current_user=Depends(get_current_user),
):
    """The user's scan history, newest first, one page at a time (cursor pagination)."""
    try:
        return await history_service.list_history(str(current_user["_id"]), limit, cursor)
    except InvalidCursor:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "code": "invalid_cursor", "message": "The page cursor is not valid. Reload the list."})


@router.get("/count", response_model=HistoryCount)
async def get_history_count(current_user=Depends(get_current_user)):
    """How many scans the user has in their history (the Profile "Scans" number)."""
    return await history_service.count_history(str(current_user["_id"]))


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(current_user=Depends(get_current_user)):
    """Delete the user's whole scan history."""
    await history_service.clear_history(str(current_user["_id"]))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history_entry(history_id: str, current_user=Depends(get_current_user)):
    """Delete one entry. 404 when it doesn't exist or belongs to someone else (same answer for both)."""
    if not await history_service.delete_entry(str(current_user["_id"]), history_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="History entry not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
