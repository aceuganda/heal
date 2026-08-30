"""Tests for the write path.

The rules being pinned: ingest is never anonymous, documents are unapproved
until approved deliberately, and re-ingesting a version overwrites rather than
duplicating.
"""
from heal.knowledge.ingest import reference_ingest
from heal.knowledge.ingest import set_approval
from heal.knowledge.ingest import supersede


def ingest(client, embedder, **kwargs):
    params = dict(
        text="Give TDF/3TC/DTG once daily. " * 20,
        title="Uganda ART Guidelines",
        actor="dr.name@facility",
        client=client,
        embedder=embedder,
    )
    params.update(kwargs)
    return reference_ingest(**params)


class TestValidation:
    def test_ingest_is_never_anonymous(self, fake_client, fake_embedder) -> None:
        """Every run has a human actor recorded against it."""
        result = ingest(fake_client, fake_embedder, actor="  ")
        assert result.status == "failed"
        assert "actor" in (result.error or "").lower()
        assert fake_client.upserts == []

    def test_a_title_is_required(self, fake_client, fake_embedder) -> None:
        assert ingest(fake_client, fake_embedder, title="").status == "failed"

    def test_empty_documents_are_rejected(self, fake_client, fake_embedder) -> None:
        result = ingest(fake_client, fake_embedder, text="   ")
        assert result.status == "failed"
        assert fake_client.upserts == []

    def test_oversized_documents_are_rejected(self, fake_client, fake_embedder) -> None:
        result = ingest(fake_client, fake_embedder, text="x" * 5_000_001)
        assert result.status == "failed"


class TestApprovalGate:
    def test_documents_are_unapproved_by_default(
        self, fake_client, fake_embedder
    ) -> None:
        """Uploading is not the same act as endorsing clinically."""
        ingest(fake_client, fake_embedder)
        points = fake_client.upserts[0]["points"]
        assert all(p.payload["approved"] is False for p in points)

    def test_approval_can_be_given_at_ingest(self, fake_client, fake_embedder) -> None:
        ingest(fake_client, fake_embedder, approved=True)
        points = fake_client.upserts[0]["points"]
        assert all(p.payload["approved"] is True for p in points)

    def test_set_approval_targets_every_chunk_of_one_source(self, fake_client) -> None:
        set_approval("src-1", approved=True, client=fake_client)
        assert fake_client.payload_sets[0]["payload"] == {"approved": True}


class TestPoints:
    def test_every_point_carries_both_vectors(self, fake_client, fake_embedder) -> None:
        ingest(fake_client, fake_embedder)
        points = fake_client.upserts[0]["points"]
        for point in points:
            assert "dense" in point.vector and "lexical" in point.vector

    def test_point_ids_are_stable_so_reingest_overwrites(
        self, fake_client, fake_embedder
    ) -> None:
        """A re-ingest of the same version must not duplicate chunks."""
        first = ingest(fake_client, fake_embedder, source_id="fixed", version="2022")
        second = ingest(fake_client, fake_embedder, source_id="fixed", version="2022")
        assert first.chunk_ids == second.chunk_ids

    def test_a_new_version_gets_new_ids(self, fake_client, fake_embedder) -> None:
        first = ingest(fake_client, fake_embedder, source_id="fixed", version="2022")
        second = ingest(fake_client, fake_embedder, source_id="fixed", version="2024")
        assert set(first.chunk_ids).isdisjoint(second.chunk_ids)

    def test_payload_carries_the_source_metadata_citations_need(
        self, fake_client, fake_embedder
    ) -> None:
        ingest(fake_client, fake_embedder, version="2022", publisher="MoH")
        payload = fake_client.upserts[0]["points"][0].payload
        assert payload["title"] == "Uganda ART Guidelines"
        assert payload["version"] == "2022"
        assert payload["publisher"] == "MoH"
        assert payload["is_current"] is True


class TestResultRecord:
    def test_result_records_counts_and_model_but_no_document_text(
        self, fake_client, fake_embedder
    ) -> None:
        """The job record is what admin/jobs reads. It carries no content."""
        result = ingest(fake_client, fake_embedder, actor="dr.name@facility")
        assert result.status == "completed"
        assert result.chunks_written > 0
        assert result.actor == "dr.name@facility"
        assert result.model
        assert "TDF/3TC/DTG" not in str(result.__dict__ | {"chunk_ids": ""})

    def test_a_store_failure_is_recorded_not_raised(
        self, fake_client, fake_embedder
    ) -> None:
        fake_client.raises = ConnectionError("qdrant down")
        result = ingest(fake_client, fake_embedder)
        assert result.status == "failed"
        assert "ConnectionError" in (result.error or "")


class TestSupersede:
    def test_supersede_keeps_one_version_current_and_deletes_nothing(
        self, fake_client
    ) -> None:
        """Superseded editions stay, so an old answer can still be explained."""
        supersede("src-1", keep_version="2024", client=fake_client)
        call = fake_client.payload_sets[0]
        assert call["payload"] == {"is_current": False}
        assert not hasattr(fake_client, "deleted")
