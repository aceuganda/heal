"""RETIRED. Extracted from danswer/db/feedback.py.

`update_document_boost` and `update_document_hidden` wrote the boost/hidden
flags straight through to Vespa; `create_doc_retrieval_feedback` recorded
per-document retrieval feedback and applied the same boost. All three are the
crowd-boost ranking control the plan retires.

`create_chat_message_feedback` -- the answer feedback Heal keeps -- stays in
danswer/db/feedback.py. It touches PostgreSQL only.

Not a pure `git mv` because these were part of a file Heal keeps.
See docs/deprecated/MOVED.md.
"""

def update_document_boost(
    db_session: Session, document_id: str, boost: int, document_index: DocumentIndex
) -> None:
    stmt = select(DbDocument).where(DbDocument.id == document_id)
    result = db_session.execute(stmt).scalar_one_or_none()
    if result is None:
        raise ValueError(f"No document found with ID: '{document_id}'")

    result.boost = boost

    update = UpdateRequest(
        document_ids=[document_id],
        boost=boost,
    )

    document_index.update([update])

    db_session.commit()


def update_document_hidden(
    db_session: Session, document_id: str, hidden: bool, document_index: DocumentIndex
) -> None:
    stmt = select(DbDocument).where(DbDocument.id == document_id)
    result = db_session.execute(stmt).scalar_one_or_none()
    if result is None:
        raise ValueError(f"No document found with ID: '{document_id}'")

    result.hidden = hidden

    update = UpdateRequest(
        document_ids=[document_id],
        hidden=hidden,
    )

    document_index.update([update])

    db_session.commit()



def create_doc_retrieval_feedback(
    message_id: int,
    document_id: str,
    document_rank: int,
    document_index: DocumentIndex,
    db_session: Session,
    clicked: bool = False,
    feedback: SearchFeedbackType | None = None,
) -> None:
    """Creates a new Document feedback row and updates the boost value in Postgres and Vespa"""
    db_doc = fetch_db_doc_by_id(document_id, db_session)

    retrieval_feedback = DocumentRetrievalFeedback(
        chat_message_id=message_id,
        document_id=document_id,
        document_rank=document_rank,
        clicked=clicked,
        feedback=feedback,
    )

    if feedback is not None:
        if feedback == SearchFeedbackType.ENDORSE:
            db_doc.boost += 1
        elif feedback == SearchFeedbackType.REJECT:
            db_doc.boost -= 1
        elif feedback == SearchFeedbackType.HIDE:
            db_doc.hidden = True
        elif feedback == SearchFeedbackType.UNHIDE:
            db_doc.hidden = False
        else:
            raise ValueError("Unhandled document feedback type")

    if feedback in [
        SearchFeedbackType.ENDORSE,
        SearchFeedbackType.REJECT,
        SearchFeedbackType.HIDE,
    ]:
        update = UpdateRequest(
            document_ids=[document_id], boost=db_doc.boost, hidden=db_doc.hidden
        )
        # Updates are generally batched for efficiency, this case only 1 doc/value is updated
        document_index.update([update])

    db_session.add(retrieval_feedback)
    db_session.commit()


def delete_document_feedback_for_documents(
    document_ids: list[str], db_session: Session
) -> None:
    """NOTE: does not commit transaction so that this can be used as part of a
    larger transaction block."""
    stmt = delete(DocumentRetrievalFeedback).where(
        DocumentRetrievalFeedback.document_id.in_(document_ids)
    )
    db_session.execute(stmt)


