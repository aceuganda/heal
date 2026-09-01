"""Tests for the retrieval playground.

The property being protected is the one that makes this feature safe to ship at
all: an administrator experimenting with a score floor must not change what any
health worker is being told at that moment. So the assertions are about
containment first -- the module config is unchanged after a request, and the
override reaches the store as an argument -- and about honesty second: what the
screen is shown must be what actually happened, including the near-misses the
floor discarded and the fact that a value was pulled into range.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from heal import config
from heal.knowledge.models import Chunk
from heal.knowledge.models import RetrievedChunk
from heal.knowledge.models import SourceRef
from heal.knowledge.settings import BOUNDS
from heal.knowledge.settings import resolve
from heal.knowledge.settings import RetrievalSettings
from heal.medical_guidance.intent import MedicalIntent
from heal.medical_guidance.understanding import Understanding
from heal.server import playground_api
from heal_app.auth.roles import UserRole
from heal_app.auth.users import current_user
from heal_app.auth import users as users_mod


TUNABLES = (
    "MIN_RETRIEVAL_SCORE",
    "HYBRID_ALPHA",
    "HYBRID_SEARCH",
    "RETRIEVAL_TOP_K",
    "CONTEXT_TOP_K",
    "MAX_CHUNKS_PER_SOURCE",
)


def chunk(
    chunk_id: str = "c1",
    score: float = 0.9,
    source_id: str = "src-1",
    title: str = "Uganda ART Guidelines",
    text: str = "Give TDF/3TC/DTG once daily.",
    ordinal: int = 0,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(
            chunk_id=chunk_id,
            text=text,
            ordinal=ordinal,
            source=SourceRef(source_id=source_id, title=title, version="2022"),
        ),
        score=score,
        dense_score=score,
        sparse_score=0.0,
    )


class FakeStore:
    """Returns scripted candidates and remembers the settings it was handed."""

    def __init__(self, scripted: list[RetrievedChunk]) -> None:
        self.scripted = scripted
        self.seen: list[RetrievalSettings] = []

    def candidates(self, query, lexical_query=None, settings=None):
        self.seen.append(settings)
        return list(self.scripted)


class FakeUser:
    """Enough of a User row for the role gate to make its decision."""

    def __init__(self, role: UserRole) -> None:
        self.role = role
        self.email = f"{role.value}@example.org"
        self.is_verified = True


@pytest.fixture(autouse=True)
def predictable_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the deployment's constants so a test asserts behaviour, not today."""
    monkeypatch.setattr(config, "KNOWLEDGE_ENABLED", True)
    monkeypatch.setattr(config, "MIN_RETRIEVAL_SCORE", 0.35)
    monkeypatch.setattr(config, "HYBRID_ALPHA", 0.6)
    monkeypatch.setattr(config, "HYBRID_SEARCH", True)
    monkeypatch.setattr(config, "RETRIEVAL_TOP_K", 20)
    monkeypatch.setattr(config, "CONTEXT_TOP_K", 5)
    monkeypatch.setattr(config, "MAX_CHUNKS_PER_SOURCE", 2)
    monkeypatch.setattr(config, "CHAT_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(config, "CLASSIFIER_MODEL", "gpt-4o-mini")


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch):
    """Install a store with scripted candidates; returns the fake."""

    def install(candidates: list[RetrievedChunk]) -> FakeStore:
        fake = FakeStore(candidates)
        monkeypatch.setattr(playground_api, "QdrantKnowledgeStore", lambda: fake)
        return fake

    return install


@pytest.fixture(autouse=True)
def no_classifier_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """The understand step is an LLM call; these tests are not about it."""

    def fake_understand(message, history=None, model_id=None):
        return Understanding(
            intent=MedicalIntent.CLINICAL_QUESTION,
            query=f"rewritten: {message}",
            original=message,
            terms=["TDF/3TC/DTG"],
            classified=True,
            rewritten=True,
            model_id=model_id or config.CLASSIFIER_MODEL,
        )

    monkeypatch.setattr(playground_api, "understand", fake_understand)


def client_as(role: UserRole) -> TestClient:
    """A client whose caller holds `role`, with the real gate in the way.

    `DISABLE_AUTH` is forced off. Left on -- which is how a local stack runs --
    every gate returns None and the 403 this file exists to prove would never
    be reached.
    """
    app = FastAPI()
    app.include_router(playground_api.router)
    app.dependency_overrides[current_user] = lambda: FakeUser(role)
    return TestClient(app)


@pytest.fixture(autouse=True)
def auth_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(users_mod, "DISABLE_AUTH", False)


def run(client: TestClient, **body) -> dict:
    payload = {"question": "dose of DTG", "retrieval_only": True, **body}
    response = client.post("/manage/playground/query", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


class TestOverridesNeverLeak:
    """The rule the whole feature stands on.

    Writing a config constant, even for the length of one request, changes the
    clinical behaviour of every conversation running at that moment and leaves
    nothing in the audit trail to explain why an answer differed.
    """

    def test_a_request_with_overrides_leaves_the_module_config_untouched(
        self, store
    ) -> None:
        store([chunk()])
        before = {name: getattr(config, name) for name in TUNABLES}

        run(
            client_as(UserRole.ADMIN),
            min_retrieval_score=0.9,
            hybrid_alpha=0.1,
            hybrid_search=False,
            retrieval_top_k=7,
            context_top_k=3,
            max_chunks_per_source=1,
        )

        assert {name: getattr(config, name) for name in TUNABLES} == before

    def test_the_override_travels_to_the_store_as_an_argument(self, store) -> None:
        fake = store([chunk()])
        run(client_as(UserRole.ADMIN), min_retrieval_score=0.5, retrieval_top_k=9)

        assert fake.seen[0].min_retrieval_score == 0.5
        assert fake.seen[0].retrieval_top_k == 9

    def test_the_next_request_is_back_on_the_deployment_defaults(self, store) -> None:
        """The failure a global would produce: yesterday's experiment persisting."""
        fake = store([chunk()])
        client = client_as(UserRole.ADMIN)

        run(client, min_retrieval_score=0.95)
        run(client)

        assert fake.seen[1].min_retrieval_score == config.MIN_RETRIEVAL_SCORE
        assert fake.seen[1].retrieval_top_k == config.RETRIEVAL_TOP_K

    def test_an_omitted_knob_is_reported_as_the_default(self, store) -> None:
        store([chunk()])
        body = run(client_as(UserRole.ADMIN), min_retrieval_score=0.5)
        settings = {s["name"]: s for s in body["settings"]}

        assert settings["min_retrieval_score"]["overridden"] is True
        assert settings["hybrid_alpha"]["overridden"] is False
        assert settings["hybrid_alpha"]["value"] == config.HYBRID_ALPHA


class TestClamping:
    """The client is never trusted. A floor of 50 refuses every question."""

    def test_a_score_above_one_is_pulled_back_to_one(self) -> None:
        settings, used = resolve({"min_retrieval_score": 7.5})
        record = {u.name: u for u in used}["min_retrieval_score"]

        assert settings.min_retrieval_score == 1.0
        assert record.clamped is True
        assert record.requested == 7.5

    def test_a_negative_score_is_pulled_up_to_zero(self) -> None:
        settings, _ = resolve({"hybrid_alpha": -3.0})
        assert settings.hybrid_alpha == 0.0

    def test_a_top_k_of_zero_becomes_one(self) -> None:
        """Zero would ask the store for nothing and report an empty library."""
        settings, _ = resolve({"retrieval_top_k": 0, "context_top_k": 0})
        assert settings.retrieval_top_k == 1
        assert settings.context_top_k == 1

    def test_an_enormous_top_k_is_bounded(self) -> None:
        settings, _ = resolve({"retrieval_top_k": 10_000})
        assert settings.retrieval_top_k == BOUNDS["retrieval_top_k"][1]

    def test_a_value_inside_the_range_is_left_alone(self) -> None:
        settings, used = resolve({"min_retrieval_score": 0.42})
        record = {u.name: u for u in used}["min_retrieval_score"]

        assert settings.min_retrieval_score == 0.42
        assert record.clamped is False

    def test_clamping_reads_the_config_without_writing_it(self) -> None:
        before = getattr(config, "MIN_RETRIEVAL_SCORE")
        resolve({"min_retrieval_score": 0.99})
        assert getattr(config, "MIN_RETRIEVAL_SCORE") == before

    def test_the_clamp_is_reported_over_the_wire(self, store) -> None:
        store([chunk()])
        body = run(client_as(UserRole.ADMIN), min_retrieval_score=9.0)
        record = {s["name"]: s for s in body["settings"]}["min_retrieval_score"]

        assert record["value"] == 1.0
        assert record["clamped"] is True
        assert record["requested"] == 9.0


class TestWhoMayTune:
    """Moving the score floor decides when the assistant refuses a dose."""

    def test_a_member_is_refused(self, store) -> None:
        store([chunk()])
        response = client_as(UserRole.MEMBER).post(
            "/manage/playground/query", json={"question": "dose of DTG"}
        )
        assert response.status_code == 403

    def test_a_member_cannot_even_read_the_options(self) -> None:
        response = client_as(UserRole.MEMBER).get("/manage/playground/options")
        assert response.status_code == 403

    def test_an_admin_is_allowed(self, store) -> None:
        store([chunk()])
        response = client_as(UserRole.ADMIN).post(
            "/manage/playground/query",
            json={"question": "dose of DTG", "retrieval_only": True},
        )
        assert response.status_code == 200

    def test_a_super_admin_is_allowed(self, store) -> None:
        """A super admin outranks an admin and must not be locked out."""
        store([chunk()])
        response = client_as(UserRole.SUPER_ADMIN).post(
            "/manage/playground/query",
            json={"question": "dose of DTG", "retrieval_only": True},
        )
        assert response.status_code == 200


class TestModelSelection:
    """A run against a model that was quietly swapped is worse than no run."""

    def test_an_unknown_chat_model_is_refused(self) -> None:
        response = client_as(UserRole.ADMIN).post(
            "/manage/playground/query",
            json={"question": "q", "chat_model": "gpt-9-imaginary"},
        )
        assert response.status_code == 422
        assert "gpt-9-imaginary" in response.text

    def test_an_unknown_classifier_model_is_refused(self) -> None:
        response = client_as(UserRole.ADMIN).post(
            "/manage/playground/query",
            json={"question": "q", "classifier_model": "not-a-model"},
        )
        assert response.status_code == 422

    def test_a_catalogue_model_is_accepted(self, store) -> None:
        store([chunk()])
        body = run(client_as(UserRole.ADMIN), classifier_model="gpt-4o")
        assert body["classifier_model"] == "gpt-4o"


class TestTheCandidateReport:
    """Tuning a floor means seeing what it is about to discard."""

    def test_a_candidate_below_the_floor_is_still_listed(self, store) -> None:
        store([chunk("high", 0.80), chunk("low", 0.34, source_id="src-2")])
        body = run(client_as(UserRole.ADMIN), min_retrieval_score=0.35)

        by_index = {c["index"]: c for c in body["candidates"]}
        assert len(by_index) == 2, "the near-miss was hidden"
        assert by_index[1]["passed_floor"] is True
        assert by_index[2]["passed_floor"] is False

    def test_a_candidate_exactly_on_the_floor_passes(self, store) -> None:
        store([chunk("edge", 0.35)])
        body = run(client_as(UserRole.ADMIN), min_retrieval_score=0.35)
        assert body["candidates"][0]["passed_floor"] is True

    def test_moving_the_floor_moves_which_candidates_pass(self, store) -> None:
        candidates = [chunk("a", 0.80), chunk("b", 0.34, source_id="src-2")]
        store(candidates)
        client = client_as(UserRole.ADMIN)

        strict = run(client, min_retrieval_score=0.5)
        lenient = run(client, min_retrieval_score=0.3)

        assert [c["passed_floor"] for c in strict["candidates"]] == [True, False]
        assert [c["passed_floor"] for c in lenient["candidates"]] == [True, True]

    def test_a_chunk_cut_by_the_diversity_cap_says_so(self, store) -> None:
        """Cut by the cap and cut by the floor are different problems."""
        store(
            [
                chunk("a1", 0.9, source_id="src-1"),
                chunk("a2", 0.8, source_id="src-1"),
                chunk("a3", 0.7, source_id="src-1"),
            ]
        )
        body = run(client_as(UserRole.ADMIN), max_chunks_per_source=2)

        third = body["candidates"][2]
        assert third["passed_floor"] is True
        assert third["survived_cap"] is False
        assert third["in_context"] is False

    def test_context_passages_carry_the_number_the_model_would_cite(
        self, store
    ) -> None:
        store([chunk("a", 0.9), chunk("b", 0.8, source_id="src-2")])
        body = run(client_as(UserRole.ADMIN))
        assert [c["citation_number"] for c in body["candidates"]] == [1, 2]

    def test_a_discarded_candidate_has_no_citation_number(self, store) -> None:
        store([chunk("a", 0.9), chunk("b", 0.10, source_id="src-2")])
        body = run(client_as(UserRole.ADMIN))
        assert body["candidates"][1]["citation_number"] is None


class TestWhatTheRunReports:
    def test_the_rewritten_query_is_shown_next_to_the_original(self, store) -> None:
        store([chunk()])
        body = run(client_as(UserRole.ADMIN), question="dose of DTG")

        assert body["understanding"]["original"] == "dose of DTG"
        assert body["understanding"]["query"] == "rewritten: dose of DTG"
        assert body["understanding"]["rewritten"] is True

    def test_the_route_says_whether_a_source_is_required(self, store) -> None:
        store([chunk()])
        body = run(client_as(UserRole.ADMIN))
        assert body["route"]["intent"] == MedicalIntent.CLINICAL_QUESTION.value
        assert body["route"]["require_source"] is False

    def test_retrieval_only_skips_generation(self, store) -> None:
        store([chunk()])
        body = run(client_as(UserRole.ADMIN))
        assert body["generated"] is False
        assert body["answer"] is None

    def test_every_stage_is_timed(self, store) -> None:
        store([chunk()])
        body = run(client_as(UserRole.ADMIN))
        for stage in ("understand_ms", "retrieve_ms", "generate_ms", "total_ms"):
            assert body["timings"][stage] >= 0

    def test_an_unreachable_store_is_reported_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class BrokenStore:
            def candidates(self, *args, **kwargs):
                raise ConnectionError("qdrant unreachable")

        monkeypatch.setattr(
            playground_api, "QdrantKnowledgeStore", lambda: BrokenStore()
        )
        body = run(client_as(UserRole.ADMIN))

        assert body["unavailable"] is True
        assert body["error"] == "ConnectionError"


class TestInputIsNotTrusted:
    def test_an_empty_question_is_refused(self) -> None:
        response = client_as(UserRole.ADMIN).post(
            "/manage/playground/query", json={"question": "   "}
        )
        assert response.status_code == 422

    def test_a_pasted_document_is_refused(self) -> None:
        response = client_as(UserRole.ADMIN).post(
            "/manage/playground/query",
            json={"question": "x" * (playground_api.MAX_QUESTION_CHARS + 1)},
        )
        assert response.status_code == 422


class TestOptions:
    def test_the_defaults_are_the_deployment_s_own_constants(self) -> None:
        body = client_as(UserRole.ADMIN).get("/manage/playground/options").json()
        assert body["defaults"]["min_retrieval_score"] == config.MIN_RETRIEVAL_SCORE
        assert body["defaults"]["hybrid_search"] is config.HYBRID_SEARCH

    def test_every_model_offered_resolves_through_the_registry(self) -> None:
        from heal.llm import get_model

        body = client_as(UserRole.ADMIN).get("/manage/playground/options").json()
        assert body["models"]
        for entry in body["models"]:
            assert get_model(entry["id"]).id == entry["id"]

    def test_the_bounds_the_screen_draws_are_the_ones_enforced(self) -> None:
        body = client_as(UserRole.ADMIN).get("/manage/playground/options").json()
        assert body["bounds"]["min_retrieval_score"] == [0.0, 1.0]
        assert body["bounds"] == {k: list(v) for k, v in BOUNDS.items()}
