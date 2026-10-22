"""Document-set write path, retired 2026-08-29.

`insert_document_set` and `update_document_set` were called only by
`server/features/document_set/api.py`, which moved to `deprecated/` on
2026-08-28. They kept `danswer/db/document_set.py` importing
`server.features.document_set.models`, a package that no longer exists on the
live tree -- which broke `import danswer.main` and so the whole API boot.

The read helpers stayed in `danswer/db/document_set.py`: three live modules
still call them. Only the write half is retired here.

Frozen text. Not imported, registered, linted, type-checked or tested.
"""
from uuid import UUID

from sqlalchemy.orm import Session

from danswer.db.document_set import _mark_document_set_cc_pairs_as_outdated__no_commit
from danswer.db.document_set import get_document_set_by_id
from danswer.db.models import DocumentSet as DocumentSetDBModel
from danswer.db.models import DocumentSet__ConnectorCredentialPair
from deprecated.danswer.server.features.document_set.models import (
    DocumentSetCreationRequest,
)
from deprecated.danswer.server.features.document_set.models import (
    DocumentSetUpdateRequest,
)


def insert_document_set(
    document_set_creation_request: DocumentSetCreationRequest,
    user_id: UUID | None,
    db_session: Session,
) -> tuple[DocumentSetDBModel, list[DocumentSet__ConnectorCredentialPair]]:
    if not document_set_creation_request.cc_pair_ids:
        raise ValueError("Cannot create a document set with no CC pairs")

    # start a transaction
    db_session.begin()

    try:
        new_document_set_row = DocumentSetDBModel(
            name=document_set_creation_request.name,
            description=document_set_creation_request.description,
            user_id=user_id,
        )
        db_session.add(new_document_set_row)
        db_session.flush()  # ensure the new document set gets assigned an ID

        ds_cc_pairs = [
            DocumentSet__ConnectorCredentialPair(
                document_set_id=new_document_set_row.id,
                connector_credential_pair_id=cc_pair_id,
                is_current=True,
            )
            for cc_pair_id in document_set_creation_request.cc_pair_ids
        ]
        db_session.add_all(ds_cc_pairs)
        db_session.commit()
    except:
        db_session.rollback()
        raise

    return new_document_set_row, ds_cc_pairs


def update_document_set(
    document_set_update_request: DocumentSetUpdateRequest, db_session: Session
) -> tuple[DocumentSetDBModel, list[DocumentSet__ConnectorCredentialPair]]:
    if not document_set_update_request.cc_pair_ids:
        raise ValueError("Cannot create a document set with no CC pairs")

    # start a transaction
    db_session.begin()

    try:
        # update the description
        document_set_row = get_document_set_by_id(
            db_session=db_session, document_set_id=document_set_update_request.id
        )
        if document_set_row is None:
            raise ValueError(
                f"No document set with ID '{document_set_update_request.id}'"
            )
        if not document_set_row.is_up_to_date:
            raise ValueError(
                "Cannot update document set while it is syncing. Please wait "
                "for it to finish syncing, and then try again."
            )

        document_set_row.description = document_set_update_request.description
        document_set_row.is_up_to_date = False

        # update the attached CC pairs
        # first, mark all existing CC pairs as not current
        _mark_document_set_cc_pairs_as_outdated__no_commit(
            db_session=db_session, document_set_id=document_set_row.id
        )
        # add in rows for the new CC pairs
        ds_cc_pairs = [
            DocumentSet__ConnectorCredentialPair(
                document_set_id=document_set_update_request.id,
                connector_credential_pair_id=cc_pair_id,
                is_current=True,
            )
            for cc_pair_id in document_set_update_request.cc_pair_ids
        ]
        db_session.add_all(ds_cc_pairs)
        db_session.commit()
    except:
        db_session.rollback()
        raise

    return document_set_row, ds_cc_pairs
