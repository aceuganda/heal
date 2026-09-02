"""Admin review of how health workers rate answers and sources.

Read-only. The score here sends a person to look at a guideline; it has no
authority over what retrieval returns. See heal/feedback/aggregate.py.
"""
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session

from heal.feedback.aggregate import MAX_RATING
from heal.feedback.aggregate import MIN_RATING
from heal.feedback.aggregate import SMOOTHING
from heal.feedback.review import rated_answers
from heal.feedback.review import rated_sources
from heal.logger import get_logger
from heal_app.auth.users import current_admin_user
from heal_app.db.engine import get_session
from heal_app.db.models import User

logger = get_logger(__name__)

# Admin, not super-admin: reading what people thought of the answers is an
# inspection tool, not a lever over what the assistant is willing to say.
router = APIRouter(prefix="/manage/feedback")

# Enough to see a pattern, few enough to render. A review screen that needs
# pagination on day one is a screen nobody finishes reading.
DEFAULT_LIMIT = 50


@router.get("/scale")
def rating_scale(_: User | None = Depends(current_admin_user)) -> dict[str, Any]:
    """The scale and the curve, so a screen never hardcodes its own copy."""
    return {
        "min_rating": MIN_RATING,
        "max_rating": MAX_RATING,
        "smoothing": SMOOTHING,
        # Both halves of the honest reading of a score.
        "neutral_score": 0.5,
        "note": (
            "Score is a bounded, confidence-weighted mean: it starts at "
            "neutral and moves further as ratings accumulate. Always read it "
            "with the count. It is a review signal and does not affect "
            "retrieval ranking."
        ),
    }


@router.get("/answers")
def worst_rated_answers(
    limit: int = DEFAULT_LIMIT,
    _: User | None = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Rated answers, worst first, with any comments left on them."""
    return [
        {
            "message_id": answer.message_id,
            "chat_session_id": answer.chat_session_id,
            "score": round(answer.rating.score, 4),
            "mean": round(answer.rating.mean, 2),
            "count": answer.rating.count,
            # Free text a user wrote. Escape it when rendering.
            "comments": answer.comments,
        }
        for answer in rated_answers(db_session, limit=min(limit, 200))
    ]


@router.get("/sources")
def worst_rated_sources(
    limit: int = DEFAULT_LIMIT,
    _: User | None = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Sources, scored by the answers that actually cited them. Worst first."""
    return [
        {
            "source_id": source.source_id,
            "title": source.title,
            "score": round(source.rating.score, 4),
            "mean": round(source.rating.mean, 2),
            "count": source.rating.count,
        }
        for source in rated_sources(db_session, limit=min(limit, 200))
    ]
