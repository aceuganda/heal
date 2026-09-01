"""Progress tracking for ingest runs.

Indexing a real guideline is minutes of CPU. Held inside one HTTP request that
is silent until it finishes, it looks identical to a hang: the browser spins,
the proxy eventually times out, and the admin is told the upload failed while
the work is still running. This is the state that lets the UI say what is
actually happening.

Deliberately in memory, not in PostgreSQL. A job is only meaningful while the
process doing the work is alive -- a restart kills the embedding thread, so a
row saying "embedding, 412/1242" would outlive the thing it describes and be a
lie. The cost is that progress is lost on restart, which is the truth anyway.

If ingest ever moves to a separate worker, this is the seam that becomes a
table.
"""
import threading
import uuid
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from typing import Any

from heal.logger import get_logger

logger = get_logger(__name__)

# Terminal states. Anything else means the thread is still working.
DONE = "completed"
FAILED = "failed"

# Jobs are small, but an admin who uploads all day should not grow the process
# without bound. Oldest finished jobs are dropped first.
MAX_TRACKED_JOBS = 50


@dataclass
class IngestJob:
    """What the admin screen needs to draw a progress bar."""

    job_id: str
    title: str
    status: str = "queued"
    phase: str = "Preparing"
    chunks_done: int = 0
    chunks_total: int = 0
    source_id: str = ""
    error: str | None = None
    started: str = ""
    finished: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def percent(self) -> int:
        """0-100. Zero rather than a division error before the total is known."""
        if self.chunks_total <= 0:
            return 0
        return min(100, int(self.chunks_done * 100 / self.chunks_total))

    @property
    def finished_running(self) -> bool:
        return self.status in (DONE, FAILED)

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "status": self.status,
            "phase": self.phase,
            "chunks_done": self.chunks_done,
            "chunks_total": self.chunks_total,
            "percent": self.percent,
            "source_id": self.source_id,
            "error": self.error,
            "started": self.started,
            "finished": self.finished,
            **self.extra,
        }


class JobRegistry:
    """Thread-safe store of in-flight and recently finished ingests.

    Every method takes the lock: the writer is an embedding thread and the
    readers are request handlers, so unsynchronised access would hand the UI
    half-updated counts.
    """

    def __init__(self, limit: int = MAX_TRACKED_JOBS) -> None:
        self._jobs: dict[str, IngestJob] = {}
        self._lock = threading.Lock()
        self._limit = limit

    def create(self, title: str) -> IngestJob:
        job = IngestJob(
            job_id=str(uuid.uuid4()),
            title=title,
            started=_now(),
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._evict_locked()
        return job

    def get(self, job_id: str) -> IngestJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: Any) -> None:
        """Set fields on a job. Unknown ids are ignored, never raised.

        A job can be evicted while its thread is still finishing, and killing
        the ingest because its progress record aged out would be absurd.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                if hasattr(job, key):
                    setattr(job, key, value)
                else:
                    job.extra[key] = value
            if job.finished_running and job.finished is None:
                job.finished = _now()

    def active(self) -> list[IngestJob]:
        with self._lock:
            return [j for j in self._jobs.values() if not j.finished_running]

    def _evict_locked(self) -> None:
        """Drop the oldest FINISHED jobs first; never evict a running one."""
        if len(self._jobs) <= self._limit:
            return
        finished = sorted(
            (j for j in self._jobs.values() if j.finished_running),
            key=lambda j: j.finished or j.started,
        )
        for job in finished:
            if len(self._jobs) <= self._limit:
                break
            del self._jobs[job.job_id]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# One registry per process, shared by the request handlers and the threads.
registry = JobRegistry()
