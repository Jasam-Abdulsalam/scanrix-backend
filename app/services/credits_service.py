from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.core.config import settings
from app.crud import crud_ai_credits


class CreditsExhausted(Exception):
    def __init__(self, resets_at: datetime):
        super().__init__("no AI credits left this week")
        self.resets_at = resets_at


@dataclass(frozen=True)
class Reservation:
    user_id: str
    action: str
    week_key: str


@dataclass(frozen=True)
class CreditBalance:
    limit: int
    remaining: int
    resets_at: datetime


async def reserve_credit(user_id: str, action: str) -> Reservation:
    """Takes 1 credit for `action` (e.g. 'ai_verdict', later 'view_alternatives'). Raises CreditsExhausted."""
    week_key = await crud_ai_credits.reserve(user_id, action, settings.AI_CREDITS_PER_WEEK)
    if week_key is None:
        raise CreditsExhausted(crud_ai_credits.current_week()[1])
    return Reservation(user_id, action, week_key)


async def refund_credit(reservation: Reservation) -> None:
    """Call when the paid action produced nothing usable."""
    await crud_ai_credits.refund(reservation.user_id, reservation.action, reservation.week_key)


async def get_balance(user_id: str, now: Optional[datetime] = None) -> CreditBalance:
    used = await crud_ai_credits.credits_used(user_id, now)
    limit = settings.AI_CREDITS_PER_WEEK
    return CreditBalance(limit=limit, remaining=max(limit - used, 0), resets_at=crud_ai_credits.current_week(now)[1])
