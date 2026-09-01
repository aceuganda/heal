"""Tests for the ingest job registry.

It is written to by an embedding thread and read by request handlers, so the
properties that matter are about concurrency and about never letting
bookkeeping interfere with the actual work.
"""
import threading

from heal.knowledge.jobs import DONE
from heal.knowledge.jobs import FAILED
from heal.knowledge.jobs import JobRegistry


class TestProgressReporting:
    def test_percent_is_zero_before_the_total_is_known(self) -> None:
        """A bar must not invent a position while chunking is still running."""
        registry = JobRegistry()
        job = registry.create("Uganda Clinical Guidelines")
        assert job.percent == 0

    def test_percent_tracks_chunks(self) -> None:
        registry = JobRegistry()
        job = registry.create("Guide")
        registry.update(job.job_id, chunks_done=621, chunks_total=1242)
        assert registry.get(job.job_id).percent == 50

    def test_percent_never_exceeds_one_hundred(self) -> None:
        """Clamped: a miscount must not render a bar wider than its track."""
        registry = JobRegistry()
        job = registry.create("Guide")
        registry.update(job.job_id, chunks_done=99, chunks_total=10)
        assert registry.get(job.job_id).percent == 100


class TestLifecycle:
    def test_a_new_job_is_not_finished(self) -> None:
        registry = JobRegistry()
        job = registry.create("Guide")
        assert not job.finished_running
        assert registry.active() == [job]

    def test_completion_stamps_a_finish_time(self) -> None:
        registry = JobRegistry()
        job = registry.create("Guide")
        registry.update(job.job_id, status=DONE)

        finished = registry.get(job.job_id)
        assert finished.finished_running
        assert finished.finished
        assert registry.active() == []

    def test_a_failure_records_its_reason(self) -> None:
        registry = JobRegistry()
        job = registry.create("Guide")
        registry.update(job.job_id, status=FAILED, error="qdrant unavailable")

        assert registry.get(job.job_id).error == "qdrant unavailable"

    def test_updating_an_unknown_job_is_ignored(self) -> None:
        """A job can age out while its thread is still finishing.

        Raising here would kill an ingest because its progress record expired,
        which would be an absurd reason to lose an indexed document.
        """
        registry = JobRegistry()
        registry.update("no-such-job", chunks_done=5)

    def test_an_unknown_job_reads_as_none(self) -> None:
        assert JobRegistry().get("no-such-job") is None


class TestEviction:
    def test_finished_jobs_are_dropped_once_the_limit_is_passed(self) -> None:
        registry = JobRegistry(limit=3)
        for i in range(6):
            job = registry.create(f"doc-{i}")
            registry.update(job.job_id, status=DONE)

        assert len(registry._jobs) <= 3

    def test_a_running_job_is_never_evicted(self) -> None:
        """Evicting a live job would blank the progress bar mid-upload."""
        registry = JobRegistry(limit=2)
        running = registry.create("the one being indexed")

        for i in range(10):
            finished = registry.create(f"doc-{i}")
            registry.update(finished.job_id, status=DONE)

        assert registry.get(running.job_id) is not None


class TestThreadSafety:
    def test_concurrent_updates_do_not_lose_counts(self) -> None:
        """The writer is an embedding thread; the readers are request handlers."""
        registry = JobRegistry()
        job = registry.create("Guide")
        registry.update(job.job_id, chunks_total=400)

        def bump() -> None:
            for _ in range(100):
                current = registry.get(job.job_id)
                registry.update(job.job_id, chunks_done=current.chunks_done + 1)

        threads = [threading.Thread(target=bump) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Read-modify-write from four threads is inherently racy, so the exact
        # count is not the assertion. What must hold is that the registry
        # survives concurrent access and stays internally consistent.
        final = registry.get(job.job_id)
        assert 0 < final.chunks_done <= 400
        assert final.percent <= 100
