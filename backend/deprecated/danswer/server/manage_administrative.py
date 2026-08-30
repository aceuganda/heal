"""RETIRED. Extracted from danswer/server/manage/administrative.py.

`doc-boosts` and `doc-hidden` wrote a per-document integer that
`translate_boost_count_to_multiplier` turned into a 0.5x-2.0x multiplier on the
retrieval score. That is a live, unaudited ranking control over clinical
sources, replaced by the admin-set versioned clinician boost in phase 2.5.

`deletion-attempt` queued a Celery task to keep document deletions consistent
between PostgreSQL and Vespa. Both are retired.

Not a pure `git mv` because these were part of a file Heal keeps.
See docs/deprecated/MOVED.md.
"""

@router.get("/admin/doc-boosts")
def get_most_boosted_docs(
    ascending: bool,
    limit: int,
    _: User | None = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> list[BoostDoc]:
    boost_docs = fetch_docs_ranked_by_boost(
        ascending=ascending, limit=limit, db_session=db_session
    )
    return [
        BoostDoc(
            document_id=doc.id,
            semantic_id=doc.semantic_id,
            # source=doc.source,
            link=doc.link or "",
            boost=doc.boost,
            hidden=doc.hidden,
        )
        for doc in boost_docs
    ]


@router.post("/admin/doc-boosts")
def document_boost_update(
    boost_update: BoostUpdateRequest,
    _: User | None = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> None:
    try:
        update_document_boost(
            db_session=db_session,
            document_id=boost_update.document_id,
            boost=boost_update.boost,
            document_index=get_default_document_index(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/doc-hidden")
def document_hidden_update(
    hidden_update: HiddenUpdateRequest,
    _: User | None = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> None:
    try:
        update_document_hidden(
            db_session=db_session,
            document_id=hidden_update.document_id,
            hidden=hidden_update.hidden,
            document_index=get_default_document_index(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))




@router.post("/admin/deletion-attempt")
def create_deletion_attempt_for_connector_id(
    connector_credential_pair_identifier: ConnectorCredentialPairIdentifier,
    _: User = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> None:
    from danswer.background.celery.celery import cleanup_connector_credential_pair_task

    connector_id = connector_credential_pair_identifier.connector_id
    credential_id = connector_credential_pair_identifier.credential_id

    cc_pair = get_connector_credential_pair(
        db_session=db_session,
        connector_id=connector_id,
        credential_id=credential_id,
    )
    if cc_pair is None:
        raise HTTPException(
            status_code=404,
            detail=f"Connector with ID '{connector_id}' and credential ID "
            f"'{credential_id}' does not exist. Has it already been deleted?",
        )

    if not check_deletion_attempt_is_allowed(connector_credential_pair=cc_pair):
        raise HTTPException(
            status_code=400,
            detail=f"Connector with ID '{connector_id}' and credential ID "
            f"'{credential_id}' is not deletable. It must be both disabled AND have"
            "no ongoing / planned indexing attempts.",
        )

    cleanup_connector_credential_pair_task.apply_async(
        kwargs=dict(connector_id=connector_id, credential_id=credential_id),
    )
