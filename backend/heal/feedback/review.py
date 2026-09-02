"""Ratings, aggregated into the review signal an admin actually reads.

This is the layer that feeds `heal/feedback/aggregate.py` from the database.
Two subjects are aggregated:

  * per ANSWER   -- one assistant message, so a specific bad answer can be read
  * per SOURCE   -- every answer that cited a guideline, so a source whose
                    answers are consistently rated poorly surfaces even when no
                    single answer looks damning

The per-source join goes through the citations actually stored on the message,
which means a source is only credited with ratings for answers that really
cited it. Attributing every rating in a session to every source retrieved would
punish a guideline for an answer it had no part in.

**This score does not touch retrieval.** It exists to send a human to look at a
guideline. See the module docstring in `aggregate.py` for why that boundary is
where it is.
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING

from heal.feedback.aggregate import aggregate
from heal.feedback.aggregate import Aggregate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RatedAnswer:
    """One assistant message and how health workers rated it."""

    message_id: int
    chat_session_id: int
    rating: Aggregate
    # Comments left on this answer, newest first. Free text written by a user,
    # so a caller rendering these must escape them.
    comments: list[str]


@dataclass(frozen=True)
class RatedSource:
    """One guideline and the ratings of the answers that cited it."""

    source_id: str
    title: str
    rating: Aggregate


def _ratings_by(rows: list[tuple[int, int | None]]) -> dict[int, list[int]]:
    """Group non-null ratings by their key, dropping unrated rows.

    Rows predating the rating column carry a thumbs value and a null rating.
    They are skipped rather than converted: a thumbs-up is somewhere in 3..4
    and inventing which would put a fabricated number into a clinical signal.
    """
    grouped: dict[int, list[int]] = {}
    for key, rating in rows:
        if rating is None:
            continue
        grouped.setdefault(key, []).append(rating)
    return grouped


def rated_answers(
    db_session: "Session", limit: int = 50, worst_first: bool = True
) -> list[RatedAnswer]:
    """Answers that have been rated, worst score first by default.

    Worst-first because the list exists to find problems. An admin opening a
    review screen sorted best-first would have to page to reach the thing they
    came for.
    """
    from heal_app.db.models import ChatMessage
    from heal_app.db.models import ChatMessageFeedback

    rows = (
        db_session.query(
            ChatMessageFeedback.chat_message_id,
            ChatMessageFeedback.rating,
            ChatMessageFeedback.feedback_text,
            ChatMessage.chat_session_id,
        )
        .join(ChatMessage, ChatMessage.id == ChatMessageFeedback.chat_message_id)
        .all()
    )

    grouped = _ratings_by([(r[0], r[1]) for r in rows])
    sessions = {r[0]: r[3] for r in rows}
    comments: dict[int, list[str]] = {}
    for message_id, _, text, _session in rows:
        if text:
            comments.setdefault(message_id, []).append(text)

    answers = [
        RatedAnswer(
            message_id=message_id,
            chat_session_id=sessions.get(message_id, 0),
            rating=aggregate(ratings),
            comments=comments.get(message_id, []),
        )
        for message_id, ratings in grouped.items()
    ]
    answers.sort(key=lambda a: a.rating.score, reverse=not worst_first)
    return answers[:limit]


def rated_sources(db_session: "Session", limit: int = 50) -> list[RatedSource]:
    """Sources, scored by the answers that cited them. Worst first.

    A source with no rated answers is omitted rather than shown at the neutral
    0.5 -- an unrated guideline and an evenly-rated one are different facts,
    and a review list is for the ones somebody has actually judged.
    """
    from heal_app.db.models import ChatMessage
    from heal_app.db.models import ChatMessageFeedback
    from heal_app.db.models import SearchDoc

    rows = (
        db_session.query(
            SearchDoc.document_id,
            SearchDoc.semantic_id,
            ChatMessageFeedback.rating,
        )
        .join(
            ChatMessage,
            ChatMessage.id == ChatMessageFeedback.chat_message_id,
        )
        .join(ChatMessage.search_docs)
        .all()
    )

    by_source: dict[str, list[int]] = {}
    titles: dict[str, str] = {}
    for document_id, semantic_id, rating in rows:
        if rating is None:
            continue
        # document_id is "source_id:version"; ratings are aggregated per source
        # across versions, because "this guideline gets bad answers" is the
        # question, and a version bump should not reset the evidence.
        source_id = str(document_id).rsplit(":", 1)[0]
        by_source.setdefault(source_id, []).append(rating)
        titles.setdefault(source_id, semantic_id or source_id)

    sources = [
        RatedSource(
            source_id=source_id,
            title=titles.get(source_id, source_id),
            rating=aggregate(ratings),
        )
        for source_id, ratings in by_source.items()
    ]
    sources.sort(key=lambda s: s.rating.score)
    return sources[:limit]
