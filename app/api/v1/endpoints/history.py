from fastapi import APIRouter, Depends
from typing import List
from app.api.deps import get_current_user
from app.crud.crud_history import get_user_history
from app.models.history import history_helper

router = APIRouter()

@router.get("/", response_model=List[dict])
async def get_history(
    limit: int = 50,
    current_user = Depends(get_current_user)
):
    """Get user's scan history"""
    history = await get_user_history(str(current_user["_id"]), limit)
    return [history_helper(h) for h in history]