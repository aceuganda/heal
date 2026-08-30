"""RETIRED. Extracted from danswer/server/query_and_chat/chat_backend.py.

This endpoint wrote an integer `boost` per document, which
`translate_boost_count_to_multiplier` turned into a 0.5x-2.0x multiplier on the
retrieval score inside `semantic_reranking`. It was a live ranking control, not
a report.

It is retired deliberately, not by accident: an unaudited crowd multiplier over
clinical sources is a control Heal should not have. Its replacement is the
admin-set, versioned, logged clinician boost described in the plan
(*Ranking and reranking*, stage 5), added in phase 2.5 only if the eval set
shows it is needed.

Not a pure `git mv` because it was part of a file Heal keeps. See
docs/deprecated/MOVED.md.
"""


@router.post("/document-search-feedback")  # noqa: F821 - frozen reference copy
def create_search_feedback(
    feedback: SearchFeedbackRequest,  # noqa: F821
    _: User | None = Depends(current_user),  # noqa: F821
    db_session: Session = Depends(get_session),  # noqa: F821
) -> None:
    """This endpoint isn't protected - it does not check if the user has access to the document
    Users could try changing boosts of arbitrary docs but this does not leak any data.
    """
    create_doc_retrieval_feedback(  # noqa: F821
        message_id=feedback.message_id,
        document_id=feedback.document_id,
        document_rank=feedback.document_rank,
        clicked=feedback.click,
        feedback=feedback.search_feedback,
        document_index=get_default_document_index(),  # noqa: F821
        db_session=db_session,
    )
