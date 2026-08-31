from collections.abc import Sequence

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from heal_app.db.models import User


def list_users(db_session: Session) -> Sequence[User]:
    """List all users. No pagination as of now, as the # of users
    is assumed to be relatively small (<< 1 million)"""
    return db_session.scalars(select(User)).unique().all()


def count_users(db_session: Session) -> int:
    """Total accounts, for the paginated admin list."""
    return int(db_session.scalar(select(func.count(User.id))) or 0)


def list_users_page(
    db_session: Session, limit: int, offset: int, email_filter: str = ""
) -> Sequence[User]:
    """One page of accounts, oldest email first.

    Ordered explicitly: without an ORDER BY, Postgres may return rows in a
    different order per query, so the same row can appear on two pages while
    another never appears at all.
    """
    stmt = select(User)
    if email_filter:
        stmt = stmt.where(User.email.ilike(f"%{email_filter}%"))
    stmt = stmt.order_by(User.email).limit(limit).offset(offset)
    return db_session.scalars(stmt).unique().all()


def count_users_matching(db_session: Session, email_filter: str = "") -> int:
    """Count for the same filter the page uses, so the totals agree."""
    stmt = select(func.count(User.id))
    if email_filter:
        stmt = stmt.where(User.email.ilike(f"%{email_filter}%"))
    return int(db_session.scalar(stmt) or 0)
