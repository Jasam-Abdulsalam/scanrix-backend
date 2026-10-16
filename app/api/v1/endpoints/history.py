from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_current_user
from app.schemas.history import HistoryRead
from app.services import history_service

router = APIRouter()


@router.get("/", response_model=List[HistoryRead])
async def get_history(
    limit: int = Query(50, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """The user's scan history, newest first, each with a product summary."""
    return await history_service.list_history(str(current_user["_id"]), limit)


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
