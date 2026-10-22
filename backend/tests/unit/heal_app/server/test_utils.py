import json
from datetime import datetime
from datetime import timezone
from uuid import uuid4

from heal_app.search.models import RetrievalDocs
from heal_app.search.models import SavedSearchDoc
from heal_app.server.utils import get_json_line


def test_a_nested_uuid_does_not_break_the_stream() -> None:
    # The final chat line carries context_docs, whose db_doc_id is a UUID that
    # a parent model's `.dict()` leaves as an object.
    doc_id = uuid4()
    docs = RetrievalDocs(
        top_documents=[
            SavedSearchDoc(
                db_doc_id=doc_id,
                document_id="src:1",
                chunk_ind=0,
                semantic_identifier="Guideline",
                link=None,
                blurb="",
                source_type="file",
                boost=0,
                hidden=False,
                metadata={},
                score=0.5,
                match_highlights=[],
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                primary_owners=None,
                secondary_owners=None,
            )
        ]
    )

    line = get_json_line({"context_docs": docs.dict()})

    assert line.endswith("\n")
    parsed = json.loads(line)
    assert parsed["context_docs"]["top_documents"][0]["db_doc_id"] == str(doc_id)
