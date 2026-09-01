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

    def test_approval_is_applied_after_every_batch_has_landed(
        self, fake_client, fake_embedder
    ) -> None:
        """Approval is the last step, never a property of the written points.

        Batches land one at a time, so a document is briefly incomplete while
        it indexes. Writing chunks pre-approved would let retrieval cite half a
        guideline; approving at the end cannot.
        """
        ingest(fake_client, fake_embedder, approved=True)

        for call in fake_client.upserts:
            assert all(p.payload["approved"] is False for p in call["points"])
        assert fake_client.payload_sets[-1]["payload"] == {"approved": True}

    def test_a_failed_ingest_never_approves(self, fake_client, fake_embedder) -> None:
        """Whatever landed stays unapproved, so it cannot be cited."""
        fake_client.raises = RuntimeError("qdrant unavailable")
        result = ingest(fake_client, fake_embedder, approved=True)

        assert result.status == "failed"
        assert fake_client.payload_sets == []

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


class TestSelectorArgument:
    """`set_payload` takes `points`; `delete` takes `points_selector`.

    Getting this wrong is a TypeError raised only against a real client, so
    every Approve, Withdraw and Make-current click in the admin UI returned a
    500 while the unit tests stayed green.
    """

    def test_approval_passes_the_selector_as_points(self, fake_client) -> None:
        set_approval("src-1", approved=True, client=fake_client)
        assert fake_client.payload_sets[0]["points"] is not None

    def test_supersede_passes_the_selector_as_points(self, fake_client) -> None:
        supersede("src-1", keep_version="2024", client=fake_client)
        assert fake_client.payload_sets[0]["points"] is not None


class TestFirstUpload:
    """The very first upload into a freshly started stack must just work.

    Before this, the collection was created by a separate setup command; skip
    it and the first upload failed on a missing collection, which reads as
    "indexing is broken" rather than "a step was missed".
    """

    def test_a_missing_collection_is_created_by_the_upload(
        self, fake_client, fake_embedder
    ) -> None:
        assert fake_client.collections == set()

        result = ingest(fake_client, fake_embedder)

        assert result.status == "completed"
        assert "test_collection" in fake_client.collections
        assert fake_client.upserts

    def test_an_existing_collection_is_left_alone(
        self, fake_client, fake_embedder
    ) -> None:
        """Re-shaping a collection means re-embedding everything; never implicit."""
        fake_client.collections.add("test_collection")

        ingest(fake_client, fake_embedder)

        assert not hasattr(fake_client, "created")


class TestBatching:
    """Ingest writes in batches and reports progress as it goes.

    Before this, everything was embedded into memory and written in one upsert
    at the end. On a real 1242-chunk guideline that meant Qdrant stayed empty
    for the whole run, there was nothing to show the admin, and a failure on
    the last chunk discarded every chunk before it.
    """

    def _long_document(self, chunks_wanted: int) -> str:
        # split_text works on characters, so make it comfortably longer than
        # CHUNK_SIZE * chunks_wanted rather than guessing the exact boundary.
        return "Give TDF/3TC/DTG once daily. " * 60 * chunks_wanted

    def test_chunks_are_written_in_batches_not_one_upsert(
        self, fake_client, fake_embedder
    ) -> None:
        result = ingest(
            fake_client,
            fake_embedder,
            text=self._long_document(4),
            batch_size=2,
        )

        assert result.status == "completed"
        assert len(fake_client.upserts) > 1, "a batched ingest makes several writes"

    def test_every_chunk_is_written_exactly_once(
        self, fake_client, fake_embedder
    ) -> None:
        """Batches must not overlap or skip: point ids come from the ordinal."""
        result = ingest(
            fake_client,
            fake_embedder,
            text=self._long_document(4),
            batch_size=2,
        )

        written = [p for call in fake_client.upserts for p in call["points"]]
        ordinals = [p.payload["ordinal"] for p in written]

        assert ordinals == sorted(ordinals)
        assert len(set(ordinals)) == len(ordinals), "an ordinal was reused"
        assert ordinals == list(range(len(ordinals)))
        assert result.chunks_written == len(written)

    def test_point_ids_are_unique_across_batches(
        self, fake_client, fake_embedder
    ) -> None:
        """The bug a missing ordinal offset causes: every batch overwrites the last."""
        ingest(fake_client, fake_embedder, text=self._long_document(4), batch_size=2)

        ids = [p.id for call in fake_client.upserts for p in call["points"]]
        assert len(set(ids)) == len(ids)

    def test_progress_is_reported_and_reaches_the_total(
        self, fake_client, fake_embedder
    ) -> None:
        seen: list[tuple[str, int, int]] = []
        result = ingest(
            fake_client,
            fake_embedder,
            text=self._long_document(4),
            batch_size=2,
            progress=lambda phase, done, total: seen.append((phase, done, total)),
        )

        assert seen, "no progress was reported at all"
        # Starts at zero so a bar can render before the first batch lands.
        assert seen[0][1] == 0
        done_values = [done for _, done, _ in seen]
        assert done_values == sorted(done_values), "progress went backwards"
        assert seen[-1][1] == result.chunks_written

    def test_a_broken_progress_callback_does_not_fail_the_ingest(
        self, fake_client, fake_embedder
    ) -> None:
        """Reporting is cosmetic; it must never cost an indexed document."""

        def explode(phase: str, done: int, total: int) -> None:
            raise RuntimeError("the UI went away")

        result = ingest(fake_client, fake_embedder, progress=explode)
        assert result.status == "completed"

    def test_work_done_before_a_failure_is_kept(
        self, fake_client, fake_embedder
    ) -> None:
        """A crash costs one batch, not the whole document."""

        class FailsOnSecondUpsert:
            def __init__(self, inner) -> None:
                self.inner = inner
                self.calls = 0

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def upsert(self, **kwargs):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("qdrant went away mid-document")
                return self.inner.upsert(**kwargs)

        client = FailsOnSecondUpsert(fake_client)
        result = ingest(
            client, fake_embedder, text=self._long_document(4), batch_size=2
        )

        assert result.status == "failed"
        assert result.chunks_written > 0, "the first batch should have survived"
        assert fake_client.upserts, "the first batch was written"
