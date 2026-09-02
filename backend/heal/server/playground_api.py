"""Admin playground: run one question through the pipeline and see everything.

The retrieval constants in `heal/config.py` decide when Heal refuses to give a
dose. `MIN_RETRIEVAL_SCORE` in particular is a clinical-safety parameter whose
current value is openly a placeholder, and it cannot be chosen from a spec --
it has to be measured against real questions and a real library. This endpoint
is the instrument for that: one question in, and out comes the rewritten query,
every candidate the store returned BEFORE the floor and the cap discarded any
of them, the route the label selected, the answer, and how long each stage took.

The near-misses are the point. `/manage/knowledge/search` already shows scores,
but it shows them for the raw query with the deployment's own constants. Tuning
means asking "what would a floor of 0.30 have let through, for the question as
retrieval actually saw it" -- and answering that must not change what anybody
else is being told at the same moment.

**Overrides are per-request and die with the request.** Nothing here writes to
`heal.config`. The tunables travel as a `RetrievalSettings` value threaded into
`search()`/`candidates()` (see heal/knowledge/settings.py), and the models are
named by id on the call. A module-level mutation would be invisible in the
audit trail and would change the clinical behaviour of every conversation
running concurrently -- which is exactly the failure this design forecloses.

The pipeline is re-run here rather than borrowed from `MedicalGuidanceAgent`,
because the agent deliberately throws the discarded candidates away. Every
stage that has a rule in it -- the route table, the floor, the cap, prompt
assembly, citation extraction -- is called, not reimplemented, so a playground
result cannot describe a pipeline that the health worker's answer did not run.
"""
import os
import time
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from pydantic import BaseModel
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from heal import config
from heal.chat.prompt_builder import PromptBuilder
from heal.chat.stream_processing import extract_citations
from heal.knowledge.models import RetrievedChunk
from heal.knowledge.settings import BOUNDS
from heal.knowledge.settings import ENV_VARS as RETRIEVAL_ENV_VARS
from heal.knowledge.settings import resolve
from heal.knowledge.settings import RetrievalSettings
from heal.knowledge.settings import SettingUsed
from heal.llm import defaults as saved_defaults
from heal.llm.settings import BOUNDS as GENERATION_BOUNDS
from heal.llm.settings import ENV_VARS as GENERATION_ENV_VARS
from heal.llm.settings import GenerationSettings
from heal.llm.settings import resolve as resolve_generation
from heal.llm.settings import SettingUsed as GenerationSettingUsed
from heal.llm.settings import VERBOSITY_LEVELS
from heal.knowledge.store import KnowledgeStore
from heal.knowledge.store import QdrantKnowledgeStore
from heal.knowledge.store import select_context
from heal.llm import all_models
from heal.llm.registry import default_model
from heal.llm.service import build_llm
from heal.llm import get_model
from heal.llm import to_provider_messages
from heal.logger import get_logger
from heal.medical_guidance import audit
from heal.medical_guidance.routes import emergency_preamble
from heal.medical_guidance.routes import MedicalIntent
from heal.medical_guidance.routes import Route
from heal.medical_guidance.routes import route_for
from heal.medical_guidance.understanding import understand
from heal.medical_guidance.understanding import Understanding
from heal_app.auth.users import current_super_admin_user
from heal_app.db.models import User

logger = get_logger(__name__)

# Same gate as user management, deliberately. Retrieval tuning is not a reading
# tool: an admin who can move the score floor can decide what the assistant is
# willing to say about a dose, so it sits with the actions that hand out
# control of the deployment rather than with the ones that merely inspect it.
router = APIRouter(prefix="/manage/playground")

# A question longer than this is not a question. Refused before it reaches a
# model, so a paste accident costs nothing.
MAX_QUESTION_CHARS = 2000

# How much of a passage to return per candidate. Long enough to judge relevance
# on screen, short enough that twenty of them are not a megabyte of JSON.
PASSAGE_CHARS = 700


class PlaygroundRequest(BaseModel):
    """One question plus the settings to run it under.

    Every override is optional and every one of them is `None` by default,
    which means "use the deployment's value". That is what lets a screen send
    only the two knobs the admin moved, and what makes "overridden" a fact
    about the request rather than a guess.
    """

    question: str

    # Both resolve through heal/llm/registry.py. An unknown id is a 422, never
    # a silent fall back to the default: a comparison run against a model that
    # was quietly swapped is worse than no comparison.
    chat_model: str | None = None
    classifier_model: str | None = None

    min_retrieval_score: float | None = None
    hybrid_alpha: float | None = None
    hybrid_search: bool | None = None
    retrieval_top_k: int | None = None
    context_top_k: int | None = None
    max_chunks_per_source: int | None = None

    # How the answer is worded, as opposed to what it may say. Separate from
    # the retrieval knobs above because they are a different kind of setting:
    # the floor decides whether a dose may be quoted, these only decide how it
    # reads. Ignored entirely when `retrieval_only` is set.
    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    # "brief" | "standard" | "detailed". Applied as a line in the prompt and as
    # a ceiling on the token cap, so trying a level here shows the same answer
    # a health worker would get if it were saved.
    verbosity: str | None = None

    # Retrieval only: skip generation entirely. Tuning a floor means running
    # the same question many times, and paying for an answer nobody reads is
    # the difference between a fast loop and a slow one.
    retrieval_only: bool = False


class UnderstandingView(BaseModel):
    """What the one understand call produced, including whether it was trusted."""

    intent: str
    original: str
    query: str
    terms: list[str]
    # The sparse half searches on this, not on `query` alone.
    lexical_query: str
    classified: bool
    # False means the query is the user's own text: either the call failed or
    # the rewrite was rejected as untrustworthy. `error` says which.
    rewritten: bool
    model: str
    error: str | None = None


class RouteView(BaseModel):
    intent: str
    retrieve: bool
    require_source: bool
    answer: bool


class CandidateView(BaseModel):
    """One candidate as the store ranked it, before anything was discarded."""

    # 1-based rank in the fused ordering. Stable within one response and what
    # the citation map points at.
    index: int
    source_id: str
    title: str
    version: str
    ordinal: int
    text: str
    truncated: bool
    dense_score: float
    sparse_score: float
    score: float
    # The two reasons a candidate does not reach the prompt, reported
    # separately: "one hundredth under the floor" and "third chunk from the
    # same guideline" call for different changes.
    passed_floor: bool
    survived_cap: bool
    # Survived everything, including the context-size trim, and was numbered
    # for the model to cite.
    in_context: bool
    # Its citation number, when it reached the prompt.
    citation_number: int | None = None


class CitationView(BaseModel):
    """A marker the answer wrote, resolved back to the candidate it points at."""

    marker: int
    candidate_index: int
    title: str
    version: str


class SettingView(BaseModel):
    name: str
    # Which stage the knob belongs to: "retrieval" decides what the assistant
    # may say, "generation" only how it reads. Sent so the screen can group
    # them rather than implying a temperature slider and a score floor carry
    # the same clinical weight.
    stage: str = "retrieval"
    # The environment variable that makes this value the default for every
    # chat. A screen that lets you tune something without saying how to keep it
    # is only half a tool.
    env_var: str = ""
    # Typed `Any` deliberately. These carry a float, an int or a bool depending
    # on the knob, and a declared union would coerce every one of them to the
    # union's first member -- turning `hybrid_search: true` into `1.0` and a
    # top-k of 20 into `20.0` on the way out.
    value: Any
    default: Any
    overridden: bool
    # True when the request asked for something outside the allowed range and
    # the server pulled it in. `requested` carries what was asked for, so the
    # screen can say so rather than showing a number nobody typed.
    clamped: bool = False
    requested: Any = None


class TimingsView(BaseModel):
    understand_ms: int
    retrieve_ms: int
    generate_ms: int
    total_ms: int


class PlaygroundResponse(BaseModel):
    question: str
    understanding: UnderstandingView
    route: RouteView
    candidates: list[CandidateView]
    citations: list[CitationView] = Field(default_factory=list)
    settings: list[SettingView]
    timings: TimingsView

    chat_model: str
    classifier_model: str

    answer: str | None = None
    # Generation was not attempted. Either the caller asked for retrieval only,
    # or the route declined, or the answer was refused for lack of a source.
    generated: bool = False
    retrieval_only: bool = False
    # The safety refusal: a dosage question with nothing approved behind it.
    refused_unsourced: bool = False

    knowledge_enabled: bool = True
    unavailable: bool = False
    error: str | None = None


class ModelView(BaseModel):
    id: str
    display_name: str
    provider: str
    selectable: bool
    # Runs on our own infrastructure. The screen needs this to offer "use the
    # internal model" as a choice rather than as an opaque catalogue id.
    self_hosted: bool = False
    # Whether this provider has a key in the environment. Offered anyway, since
    # a run that fails for a missing key is a clearer answer than an absence.
    configured: bool
    notes: str = ""


class VerbosityView(BaseModel):
    """One answer length an admin can choose."""

    name: str
    label: str
    hint: str
    # Tokens this level is allowed. The applied cap is the smaller of this and
    # `max_output_tokens`, so the screen can explain why a "detailed" answer
    # still stops at the configured ceiling.
    budget: int


class OptionsResponse(BaseModel):
    """Everything the screen needs to draw its controls truthfully.

    The defaults and the bounds come from the server because the server is what
    enforces them. A frontend carrying its own copy would eventually disagree,
    and the screen would then mark a value as "default" that was not.
    """

    models: list[ModelView]
    chat_model: str
    classifier_model: str
    # `Any` for the same reason as SettingView.value: these are floats, ints
    # and one bool, and a union would flatten them all to the first member.
    #
    # These are the EFFECTIVE defaults -- the environment with any saved
    # override applied -- because that is what the deployment actually runs on,
    # and it is the only honest baseline for the screen's "changed" marks.
    defaults: dict[str, Any]
    bounds: dict[str, list[float]]
    knowledge_enabled: bool

    # What the environment alone says, before anything saved. Sent so the
    # screen can offer "back to the environment" as a real choice and show what
    # that would mean.
    env_defaults: dict[str, Any] = Field(default_factory=dict)
    # Knob -> "saved" or "environment". A value equal to the environment's is
    # still reported as saved: somebody chose it, and hiding that would make a
    # deliberate decision look like a default nobody has reviewed.
    sources: dict[str, str] = Field(default_factory=dict)
    verbosity_levels: list[VerbosityView] = Field(default_factory=list)
    # Byline for the saved settings; both null when nothing has been saved.
    updated_at: str | None = None
    updated_by: str | None = None


class SavedDefaults(BaseModel):
    """A change to what the deployment runs on, for every chat, from now on.

    Every field is optional, and the three states are distinguished on purpose:

      * absent  -- leave this knob exactly as it is
      * null    -- clear it back to the environment variable
      * a value -- save it

    The set of fields the body actually carried is what separates the first
    two, which is why this uses a plain optional rather than a sentinel:
    "reset temperature" and "I did not touch temperature" are different
    requests and the API has to be able to hear the difference.
    """

    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    verbosity: str | None = None
    chat_model: str | None = None
    classifier_model: str | None = None

    class Config:
        # An unknown key is a 422, not a shrug. Saving is the one action here
        # that changes what health workers receive, and a request that names a
        # knob this endpoint will not write -- a retrieval setting, say, or a
        # misspelling -- has to be told so rather than quietly half-applied.
        extra = "forbid"


class SavedDefaultsResponse(BaseModel):
    """The deployment's settings after a save, as the server now reads them."""

    defaults: dict[str, Any]
    env_defaults: dict[str, Any]
    sources: dict[str, str]
    # The knobs this request actually changed, so the screen can confirm the
    # change rather than the whole state.
    changed: dict[str, Any]
    updated_at: str | None = None
    updated_by: str | None = None


def _resolve_model(model_id: str | None, field: str) -> str:
    """Check an override against the catalogue, or refuse the request.

    422 rather than a fall back to the default. The whole value of this screen
    is that the settings panel describes the run that produced the result; a
    silent substitution would make it lie.
    """
    if not model_id:
        return ""
    try:
        return get_model(model_id).id
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field}: {exc}") from exc


def _understanding_view(result: Understanding) -> UnderstandingView:
    return UnderstandingView(
        intent=result.intent.value,
        original=result.original,
        query=result.query,
        terms=list(result.terms),
        lexical_query=result.lexical_query,
        classified=result.classified,
        rewritten=result.rewritten,
        model=result.model_id,
        error=result.error,
    )


def _settings_view(
    used: list[SettingUsed] | list[GenerationSettingUsed],
    stage: str = "retrieval",
) -> list[SettingView]:
    env_vars = GENERATION_ENV_VARS if stage == "generation" else RETRIEVAL_ENV_VARS
    return [
        SettingView(
            name=item.name,
            stage=stage,
            env_var=env_vars.get(item.name, ""),
            value=item.value,
            default=item.default,
            overridden=item.overridden,
            clamped=item.clamped,
            requested=item.requested,
        )
        for item in used
    ]


def _candidate_views(
    candidates: list[RetrievedChunk],
    passed_floor: frozenset[str],
    survived_cap: frozenset[str],
    context: list[RetrievedChunk],
) -> list[CandidateView]:
    """Every candidate, in rank order, annotated with what happened to it."""
    citation_of = {c.chunk.chunk_id: i for i, c in enumerate(context, start=1)}
    views: list[CandidateView] = []
    for index, item in enumerate(candidates, start=1):
        chunk_id = item.chunk.chunk_id
        text = item.text
        views.append(
            CandidateView(
                index=index,
                source_id=item.source.source_id,
                title=item.source.title,
                version=item.source.version,
                ordinal=item.chunk.ordinal,
                text=text[:PASSAGE_CHARS],
                truncated=len(text) > PASSAGE_CHARS,
                dense_score=round(item.dense_score, 4),
                sparse_score=round(item.sparse_score, 4),
                score=round(item.score, 4),
                passed_floor=chunk_id in passed_floor,
                # A candidate below the floor never reached the cap. Reporting
                # it as "survived" would suggest the cap was what kept it.
                survived_cap=chunk_id in passed_floor and chunk_id in survived_cap,
                in_context=chunk_id in citation_of,
                citation_number=citation_of.get(chunk_id),
            )
        )
    return views


def _citation_views(
    answer: str,
    context: list[RetrievedChunk],
    candidates: list[RetrievedChunk],
) -> list[CitationView]:
    """Markers the answer actually wrote, resolved to candidate rows.

    Marker N is context passage N, which the prompt numbered from 1. A marker
    outside that range is dropped, exactly as the chat path drops it: the model
    occasionally writes [9] when it was handed five passages, and a citation
    pointing at nothing is the one thing this whole surface exists to catch.

    The number the reader sees is not the number of the row it points at -- the
    floor and the cap sit between them -- so the candidate index is looked up
    by chunk id rather than assumed to be the marker.
    """
    positions = {c.chunk.chunk_id: i for i, c in enumerate(candidates, start=1)}
    views: list[CitationView] = []
    for marker in extract_citations(answer):
        if marker > len(context):
            logger.warning(
                "Answer cited [%d] but only %d passages were provided",
                marker,
                len(context),
            )
            continue
        chunk = context[marker - 1]
        views.append(
            CitationView(
                marker=marker,
                candidate_index=positions.get(chunk.chunk.chunk_id, marker),
                title=chunk.source.title,
                version=chunk.source.version,
            )
        )
    return views


@router.get("/options")
def playground_options(
    _: User | None = Depends(current_super_admin_user),
) -> OptionsResponse:
    """Model catalogue and the deployment's own defaults, retrieval and generation."""
    defaults = RetrievalSettings()
    generation_defaults = GenerationSettings()
    effective = saved_defaults.effective()
    updated_at, updated_by = saved_defaults.last_change()
    return OptionsResponse(
        models=[
            ModelView(
                id=spec.id,
                display_name=spec.display_name,
                provider=spec.provider,
                selectable=spec.selectable,
                self_hosted=spec.self_hosted,
                # We host it, so there is no third-party key to hold. Whether
                # it answers is a runtime question the run itself reports.
                configured=spec.self_hosted
                or bool(os.environ.get(spec.api_key_env))
                or (
                    spec.provider == "openai" and bool(os.environ.get("GEN_AI_API_KEY"))
                ),
                notes=spec.notes,
            )
            for spec in all_models()
        ],
        chat_model=effective["chat_model"],
        classifier_model=effective["classifier_model"],
        defaults={
            "temperature": generation_defaults.temperature,
            "max_output_tokens": generation_defaults.max_output_tokens,
            "top_p": generation_defaults.top_p,
            "verbosity": generation_defaults.verbosity,
            "min_retrieval_score": defaults.min_retrieval_score,
            "hybrid_alpha": defaults.hybrid_alpha,
            "hybrid_search": defaults.hybrid_search,
            "retrieval_top_k": defaults.retrieval_top_k,
            "context_top_k": defaults.context_top_k,
            "max_chunks_per_source": defaults.max_chunks_per_source,
        },
        bounds={
            name: [low, high]
            for name, (low, high) in {**BOUNDS, **GENERATION_BOUNDS}.items()
        },
        knowledge_enabled=config.KNOWLEDGE_ENABLED,
        env_defaults=saved_defaults.env_defaults(),
        sources=saved_defaults.sources(),
        verbosity_levels=[
            VerbosityView(
                name=level.name,
                label=level.label,
                hint=level.hint,
                budget=level.budget,
            )
            for level in VERBOSITY_LEVELS.values()
        ],
        updated_at=updated_at.isoformat() if updated_at else None,
        updated_by=updated_by,
    )


@router.put("/defaults")
def save_defaults(
    request: SavedDefaults,
    user: User | None = Depends(current_super_admin_user),
) -> SavedDefaultsResponse:
    """Change what every chat runs on, not just this screen's next run.

    This is the one endpoint here that outlives its request. Everything else in
    this module is deliberately per-run -- see the module docstring -- and the
    difference is not a detail: a temperature saved here is the temperature the
    next health worker's answer is written at.

    Which is why the retrieval knobs are NOT settable through it. The score
    floor decides whether a dose may be quoted at all; it is a clinical-safety
    parameter, it is set from measured results on the eval set, and it stays in
    the deployment's environment where changing it is a reviewed act.
    """
    # Only what the caller actually sent. An absent field is untouched; a field
    # sent as null is a deliberate reset to the environment. `__fields_set__`
    # is pydantic v1's record of which is which -- without it the two collapse
    # into "null" and every save would clear the knobs it did not mention.
    sent = request.__fields_set__
    values = {
        name: getattr(request, name) for name in saved_defaults.FIELDS if name in sent
    }
    if not values:
        raise HTTPException(status_code=422, detail="No settings were provided")

    cleaned = {name: _validated(name, value) for name, value in values.items()}

    try:
        effective = saved_defaults.save(
            cleaned, actor_id=user.id if user is not None else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    audit.emit(
        audit.SettingsChangeEvent(
            changed=cleaned,
            actor_id=str(user.id) if user is not None else None,
        )
    )

    updated_at, updated_by = saved_defaults.last_change()
    return SavedDefaultsResponse(
        defaults=effective,
        env_defaults=saved_defaults.env_defaults(),
        sources=saved_defaults.sources(),
        changed=cleaned,
        updated_at=updated_at.isoformat() if updated_at else None,
        updated_by=updated_by,
    )


def _validated(name: str, value: Any) -> Any:
    """One saved value, checked the way the run path would check it.

    Null passes straight through: it means "clear this back to the
    environment", and there is nothing to validate about not having a value.

    Numbers are CLAMPED rather than rejected, exactly as `resolve()` clamps a
    per-run override -- a slider at its end is a legitimate thing to ask for.
    Model ids and verbosity levels are REFUSED instead, because there is no
    nearest valid value to pull them towards and a silent substitution would
    save a model the admin did not choose.
    """
    if value is None:
        return None

    if name in ("chat_model", "classifier_model"):
        return _resolve_model(str(value), name)

    if name == "verbosity":
        if str(value) not in VERBOSITY_LEVELS:
            raise HTTPException(
                status_code=422,
                detail=f"verbosity: unknown level '{value}'. Known: "
                f"{', '.join(VERBOSITY_LEVELS)}",
            )
        return str(value)

    low, high = GENERATION_BOUNDS[name]
    bounded = max(low, min(high, float(value)))
    return int(bounded) if isinstance(value, int) else bounded


@router.post("/query")
async def run_query(
    request: PlaygroundRequest,
    _: User | None = Depends(current_super_admin_user),
) -> PlaygroundResponse:
    """Run one question and report every stage of it.

    Off the event loop in full: the understand call, the vector search and the
    generation are all blocking, and running any of them inline froze the whole
    API -- `/health` included -- for the length of the request.
    """
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="A question is required")
    if len(question) > MAX_QUESTION_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"A question must be at most {MAX_QUESTION_CHARS} characters",
        )

    chat_model = _resolve_model(request.chat_model, "chat_model")
    classifier_model = _resolve_model(request.classifier_model, "classifier_model")

    settings, used = resolve(
        {
            "min_retrieval_score": request.min_retrieval_score,
            "hybrid_alpha": request.hybrid_alpha,
            "hybrid_search": request.hybrid_search,
            "retrieval_top_k": request.retrieval_top_k,
            "context_top_k": request.context_top_k,
            "max_chunks_per_source": request.max_chunks_per_source,
        }
    )

    generation, generation_used = resolve_generation(
        {
            "temperature": request.temperature,
            "max_output_tokens": request.max_output_tokens,
            "top_p": request.top_p,
            "verbosity": request.verbosity,
        }
    )

    return await run_in_threadpool(
        _run,
        question=question,
        chat_model=chat_model,
        classifier_model=classifier_model,
        settings=settings,
        used=used,
        generation=generation,
        generation_used=generation_used,
        retrieval_only=request.retrieval_only,
    )


def _run(
    question: str,
    chat_model: str,
    classifier_model: str,
    settings: RetrievalSettings,
    used: list[SettingUsed],
    retrieval_only: bool,
    generation: GenerationSettings | None = None,
    generation_used: list[GenerationSettingUsed] | None = None,
    store: KnowledgeStore | None = None,
) -> PlaygroundResponse:
    """The pipeline, instrumented. Synchronous; called in a worker thread.

    `store` is injectable so this can be exercised without Qdrant, which is the
    same reason `QdrantKnowledgeStore` takes its client as an argument.
    """
    started = time.perf_counter()

    mark = time.perf_counter()
    result = understand(question, model_id=classifier_model or None)
    understand_ms = _elapsed_ms(mark)

    route = route_for(result.intent)
    response = PlaygroundResponse(
        question=question,
        understanding=_understanding_view(result),
        route=RouteView(
            intent=result.intent.value,
            retrieve=route.retrieve,
            require_source=route.require_source,
            answer=route.answer,
        ),
        candidates=[],
        settings=_settings_view(used, "retrieval")
        + _settings_view(generation_used or [], "generation"),
        timings=TimingsView(
            understand_ms=understand_ms, retrieve_ms=0, generate_ms=0, total_ms=0
        ),
        chat_model=chat_model or config.CHAT_MODEL,
        classifier_model=result.model_id,
        retrieval_only=retrieval_only,
        knowledge_enabled=config.KNOWLEDGE_ENABLED,
    )

    # The route declined outright. No retrieval, no model call -- the decline
    # text is fixed, and showing it is more honest than a blank result.
    if not route.answer:
        response.answer = route.decline_message
        response.timings.total_ms = _elapsed_ms(started)
        return response

    candidates: list[RetrievedChunk] = []
    context: list[RetrievedChunk] = []
    retrieve_ms = 0
    if route.retrieve and config.KNOWLEDGE_ENABLED:
        mark = time.perf_counter()
        store = store or QdrantKnowledgeStore()
        try:
            candidates = store.candidates(result.query, result.lexical_query, settings)
        except Exception as exc:  # noqa: BLE001 -- reported, never a 500
            logger.error("Playground retrieval failed: %s", type(exc).__name__)
            response.unavailable = True
            response.error = type(exc).__name__
            response.timings.retrieve_ms = _elapsed_ms(mark)
            response.timings.total_ms = _elapsed_ms(started)
            return response

        selection = select_context(candidates, settings)
        context = selection.context
        retrieve_ms = _elapsed_ms(mark)
        response.candidates = _candidate_views(
            candidates, selection.passed_floor, selection.survived_cap, context
        )
    response.timings.retrieve_ms = retrieve_ms

    # The one place citing nothing beats citing weakly, mirrored from the
    # agent: a dose under a citation marker carries authority the passage has
    # not earned. Shown here so an admin can see the floor cause the refusal.
    if route.require_source and config.KNOWLEDGE_ENABLED and not context:
        response.refused_unsourced = True
        response.timings.total_ms = _elapsed_ms(started)
        return response

    if retrieval_only:
        response.timings.total_ms = _elapsed_ms(started)
        return response

    mark = time.perf_counter()
    answer, error = _generate(question, route, result, context, chat_model, generation)
    response.timings.generate_ms = _elapsed_ms(mark)
    response.timings.total_ms = _elapsed_ms(started)

    if error is not None:
        response.error = error
        return response

    response.answer = answer
    response.generated = True
    response.citations = _citation_views(answer, context, candidates)
    return response


def _generate(
    question: str,
    route: Route,
    result: Understanding,
    context: list[RetrievedChunk],
    chat_model: str,
    generation: GenerationSettings | None = None,
) -> tuple[str, str | None]:
    """One non-streaming completion, built exactly as the chat path builds it.

    Collected rather than streamed: this response is a report, and there is no
    reader waiting on the first token. The emergency preamble is still
    prepended, because an answer shown here without it would not be the answer
    a health worker would have received.
    """
    gen = generation or GenerationSettings()
    builder = PromptBuilder(
        knowledge_enabled=config.KNOWLEDGE_ENABLED,
        route_instruction=route.instruction,
        # The verbosity level is half a prompt and half a token cap, and the
        # prompt half is the one that shapes the answer. Omitting it here would
        # show an admin a longer answer than the level they picked produces.
        length_instruction=gen.instruction,
        context=[c.text for c in context],
        context_labels=[c.source.label() for c in context],
    )
    prefix = emergency_preamble() if result.intent is MedicalIntent.EMERGENCY else ""

    try:
        spec = get_model(chat_model) if chat_model else default_model()
        llm = build_llm(spec, generation=gen)
        text = "".join(llm.stream(to_provider_messages(builder.build(question))))
    except Exception as exc:  # noqa: BLE001 -- the report carries the failure
        logger.error("Playground generation failed: %s", exc)
        return "", f"{type(exc).__name__}: {exc}"

    return prefix + text, None


def _elapsed_ms(since: float) -> int:
    return int((time.perf_counter() - since) * 1000)
