# Heal: keep-and-simplify plan

**Status:** scaffolding — decisions locked, no application code written or removed yet.
**Revised:** 2026-08-26
**Target pilot date:** 2026-09-09 (two weeks)
**Fork baseline:** Danswer snapshot merged 2024-01-25 (`8349ed5`); Heal-specific commits follow it.
**Runtime companion:** `docs/runtime-architecture.md` — which services run at each
stage between today and the target, and the code holding each one in place.

## Goal

Keep the part of Heal that is valuable to health workers: a fast, mobile-friendly
English/Luganda chat experience, safe answers, answer feedback, and downloadable
conversation history. Replace the two private translation services with the
OpenAI API, retire Vespa and the enterprise-search machinery built around it, and
reintroduce retrieval as one small, auditable Qdrant-backed module.

The first release is **chat-first**. It must not claim answers are grounded in
private documents until the curated knowledge path is deliberately added and
measured.

---

## Locked decisions

These are settled. Anything in this document that contradicts them is a bug in
this document.

| # | Decision | Consequence |
| --- | --- | --- |
| D1 | **Qdrant** is the vector store. PostgreSQL is the system of record. | pgvector is a documented fallback only, with a written trigger (see *Fallback trigger*). Never run both for the same collection. |
| D2 | **Design A: translate-then-retrieve.** Luganda in → English → retrieve in English → answer in English → Luganda out. | The retrieval corpus and the embedding model are **English-only**. Luganda quality becomes a translation-quality problem, which is testable and fixable. |
| D3 | **One agent module:** `MedicalGuidanceAgent`. Retrieval only. No tools, no planner, no autonomy. | No agent selector, no tool loop, no multi-agent handoff, no background agent. |
| D4 | **Intent classification is kept — with a medical label set.** | The Danswer keyword/semantic/QA TensorFlow classifier is deprecated. Intent becomes a safety-routing control, not a search-mode switch. |
| D5 | **Nothing is deleted in this cycle.** Retired code moves to `deprecated/`. | Reviewable, revertable, and safe under a two-week deadline. Deletion is a separate, later change. |
| D6 | **384-dimension embeddings**, one local embedding worker, no reranker at launch. | Dimension is frozen before first ingest. Changing it later means a new collection and a full re-embed. |
| D7 | **New Alembic baseline.** The inherited 49-migration chain is squashed into `0001_heal_baseline`; the old chain moves to `deprecated/alembic_danswer/`. | Production is **stamped**, never upgraded. The prod-vs-fresh schema diff is the acceptance gate. |

### Fallback trigger (D1)

Switch to pgvector only if, before first ingest, the deployment target refuses a
third stateful service *or* Qdrant fails the ARM64 / backup / restore check in
Day 8. The `KnowledgeStore` interface exists so this is a one-file change.

---

## Current architecture — as it runs today

```text
                     Browser / PWA / Capacitor shell
                                  |
                                  v
                        Next.js 14  (web/src/app)
                     chat/  search/  admin/  auth/
                                  |  POST /chat/send-message  (SSE)
                                  v
    ==========================  FastAPI api_server  ==========================
    backend/danswer/chat/process_message.py :: stream_chat_message   (543 lines)
    |
    |-- 1. is_luganda?  --> translate_to_english(text)
    |                        utils/translation.py -> http://65.108.33.93:4002
    |                        plain HTTP, hard-coded IP, no auth, no timeout
    |
    |-- 2. persist user message                    -> PostgreSQL
    |
    |-- 3. run_search?
    |        retrieval_options == AUTO
    |          -> check_if_need_search()           -> LLM prompt
    |             secondary_llm_flows/choose_search.py
    |
    |-- 4. history_based_query_rephrase()          -> LLM prompt
    |
    |-- 5. retrieval_preprocessing()               search/request_preprocessing.py
    |        -> query_intent()                     search/danswer_helper.py
    |             IntentModel -> TFDistilBert "danswer/intent-model"
    |             3 classes: keyword | semantic | QA
    |             emits SearchType + QueryFlow
    |        -> filter extraction, ACL, time cutoff
    |
    |-- 6. full_chunk_search_generator()           -> VespaIndex
    |        embed query   -> gte-small (384d)     model_server / local torch
    |        search        -> Vespa 8.277.17
    |        rerank        -> 2x English MS MARCO cross-encoders
    |
    |-- 7. LLM chunk filter                        -> LLM prompt
    |
    |-- 8. generate_ai_chat_response()             -> LiteLLM -> gpt-3.5-turbo
    |        extract_citations_from_stream()
    |
    |-- 9. is_luganda? --> translate_to_luganda()  -> http://65.108.33.93:5000
    |
    '-- 10. persist assistant message + citations  -> PostgreSQL
    ==========================================================================

    Supporting services (docker-compose.dev.yml):
      api_server | background (Celery+Beat+Dask+Supervisor) | web_server
      postgres:15.2 | vespa:8.277.17 | nginx:1.23.4
      + optional model_server (Dockerfile.model_server)

    Python weight: torch, tensorflow==2.14.0, transformers,
      sentence-transformers==2.2.2, nltk, dask, celery, supervisor,
      llama-index, langchain, playwright, + ~20 connector SDKs
```

Three properties of this flow drive the whole plan:

1. **It is one function.** Steps 1–10 are inline branches in
   `stream_chat_message`. Nothing can be tested without Vespa running.
2. **Every branch assumes Vespa.** `SearchType`, `QueryFlow`, the intent model,
   the rerankers and the chunk filter all exist to tune one hybrid search engine.
3. **Luganda is already translated away at step 1.** The retrieval stack has
   never seen a Luganda token. Design A formalises what the code already does.

---

## Target architecture — health-worker-first

```text
                     Browser / PWA / Capacitor shell
                                  |
                                  v
                        Next.js 14  (web/src/app)
                          chat/  admin/  auth/
                                  |  POST /chat/send-message  (SSE, unchanged contract)
                                  v
    ============================  FastAPI Heal API  ==========================

    heal/medical_guidance/  MedicalGuidanceAgent          <-- the only agent
    |
    |-- 1. LanguageService.to_english(text, src=lug)
    |        heal/language/ -> OpenAI Responses API
    |        strict translation instruction, timeout, retry, no content logged
    |
    |-- 2. persist user message (orig + english)          -> PostgreSQL
    |
    |-- 3. MedicalIntent.classify(text_en, history)       -> one structured call
    |        EMERGENCY | DOSAGE_OR_MEDICATION | CLINICAL_QUESTION
    |        GENERAL_HEALTH_INFO | ADMIN_OR_SMALLTALK | OUT_OF_SCOPE
    |        (replaces query_intent + check_if_need_search, both of them)
    |
    |-- 4. route on intent
    |        EMERGENCY            -> escalation copy FIRST, then continue
    |        DOSAGE_OR_MEDICATION -> retrieval REQUIRED; refuse if no source
    |        CLINICAL_QUESTION    -> retrieve + cite
    |        GENERAL_HEALTH_INFO  -> retrieve if available
    |        ADMIN_OR_SMALLTALK   -> no retrieval, no citation
    |        OUT_OF_SCOPE         -> decline + redirect, stop
    |
    |-- 5. KnowledgeStore.search(query_en, k)   [phase 2 only]
    |        heal/knowledge/
    |        embed query   -> embedding_worker (384d, English)
    |        PRE-filter    -> approved == true AND current source_version
    |                         (Qdrant payload filter, before ANN — not after)
    |        rank          -> cosine similarity, descending      <- primary rank
    |        score floor   -> below MIN_RETRIEVAL_SCORE, return nothing
    |        diversity cap -> max N chunks per source document
    |        hydrate       -> PostgreSQL (canonical text + source metadata)
    |        (no reranker at launch — see "Ranking and reranking")
    |
    |-- 6. PromptBuilder.build()                          <-- borrowed from Onyx
    |        versioned safety instruction + history + approved context
    |
    |-- 7. OpenAI Responses API (stream)
    |        StreamProcessor extracts citations            <-- borrowed from Onyx
    |
    |-- 8. LanguageService.to_luganda(answer)  if src=lug
    |
    '-- 9. persist assistant message + citations + audit event -> PostgreSQL
    ==========================================================================

    Phase 1 services:  api_server | web_server | postgres
    Phase 2 adds:      qdrant  +  embedding_worker (on-demand ingest only)

    Removed from the runtime path: Vespa, Celery, Beat, Dask, Supervisor,
      Slack listener, connector polling, model_server fleet, tensorflow,
      English rerankers, LLM chunk filter, query rephrase, search UI.
```

### Why this shape is the light one

- **One LLM call decides routing** (step 3) where the old flow made three
  separate secondary-LLM round trips (`check_if_need_search`, rephrase, chunk
  filter). Fewer calls, lower latency, cheaper, and the decision is auditable.
- **Retrieval is a direct call, not a tool.** The model never chooses whether to
  search; the intent router does, deterministically, from a fixed table.
- **Phase 1 has no background process at all.** A request comes in, an answer
  streams out, rows are written. Nothing else runs.

---

## Deprecation policy (D5)

Under a two-week deadline, deletion is the risky operation and moving is the
cheap one. Nothing gets deleted in this cycle.

```text
backend/deprecated/danswer/            # retired backend modules, import-frozen
backend/deprecated/alembic_danswer/    # the inherited 49-migration chain
web/src/deprecated/                    # retired frontend routes and components
deployment/deprecated/                 # retired compose/k8s definitions
docs/deprecated/                       # notes explaining each move
```

**Rules — these are the safety rails, follow them exactly:**

1. Move with `git mv` only. No edits in the same commit as a move; a move commit
   must show 100% rename similarity so review is trivial.
2. Nothing under `deprecated/` may be imported by live code. The gate is a
   single grep in CI: `grep -rn "deprecated" backend/heal web/src --include=* `
   must return no import statements.
3. Nothing under `deprecated/` is registered: no router included, no Celery task,
   no compose service, no Alembic head.
4. `deprecated/` is excluded from lint, type-check, and test collection. It is
   frozen text, not maintained code.
5. **Alembic is the one exception to "move only":** the inherited 49-migration
   chain is squashed into a new Heal baseline and the old chain moves to
   `deprecated/alembic_danswer/`. See *Database migrations* below — it has its
   own procedure because it is the only step that can damage live data.
   Dropping retired tables is still a separate forward migration, after the
   pilot. Unused tables stay for now.
6. Every move gets a one-line entry in `docs/deprecated/MOVED.md`:
   original path, new path, date, reason, and what replaces it.
7. Deletion is a separate change after the pilot runs clean for two weeks.

### Deprecation map

| Path | Action | Reason |
| --- | --- | --- |
| `backend/danswer/document_index/vespa/` | move | Vespa retired; `KnowledgeStore` replaces it |
| `backend/danswer/indexing/` | move | connector-driven indexing replaced by on-demand ingest |
| `backend/danswer/search/` | move | search-mode selection has no meaning with one collection |
| `backend/danswer/search/danswer_helper.py` | move | `query_intent`, keyword/semantic/QA — superseded by `MedicalIntent` |
| `backend/danswer/search/search_nlp_models.py` | **split** | keep the embedding path → `heal/knowledge/`; move `IntentModel` + cross-encoders |
| `backend/danswer/secondary_llm_flows/` | move | `check_if_need_search`, rephrase, chunk filter → folded into intent |
| `backend/danswer/connectors/` | move | ~20 external connectors, none serve the MVP |
| `backend/danswer/background/` | move | Celery/Beat/Dask worker fleet |
| `backend/danswer/danswerbot/` | move | Slack bot |
| `backend/danswer/one_shot_answer/` | move | search-page answer path |
| `backend/danswer/utils/translation.py` | move | hard-coded HTTP to `65.108.33.93` → `LanguageService` |
| `backend/alembic/versions/*.py` (all 49) | **squash + move** | new `0001_heal_baseline`; old chain to `deprecated/alembic_danswer/` — see *Database migrations* |
| `backend/model_server/` | move | replaced by a scoped `embedding_worker`; `custom_models.py` is the only `import tensorflow` |
| `backend/Dockerfile.model_server`, `supervisord.conf` | move | no worker fleet in phase 1 |
| `backend/danswer/access/` | move | source-level ACL; not needed with one approved library |
| `web/src/app/search/`, `web/src/components/search/`, `web/src/lib/search/` | move | search page retired |
| `web/src/app/chat/documentSidebar/` | move | document-selection UI |
| `web/src/app/admin/{connectors,connector,add-connector,indexing}/` | move | connector + indexing admin |
| `web/src/app/admin/documents/{explorer,sets}/` | move | replaced by `admin/sources` in phase 2 |
| `web/src/app/admin/documents/feedback/` | **replace, not just move** | it writes `chunk.boost`, a live ranking input — see *Admin surface* |
| `web/src/app/admin/bot/` | move | Slack bot retired |
| `web/src/app/admin/personas/` | move | one fixed agent, no persona editor |
| `backend/danswer/server/features/{persona,prompt,document_set}/` | move | backends for the above |
| `backend/danswer/server/documents/{connector,credential,cc_pair}.py` | move | connector admin backend |
| `backend/danswer/server/manage/slack_bot.py` | move | Slack bot admin backend |
| `deployment/kubernetes/vespa-service-deployment.yaml` | move | |
| `deployment/kubernetes/background-deployment.yaml` | move | the whole supervisord fleet — see *What used to run in the background* |
| `deployment/docker_compose/docker-compose.prod*.yml` | move | one tested compose file first |

**Kept and refactored, not moved:** `chat/`, `db/`, `llm/`, `auth/`,
`server/query_and_chat/`, `configs/`, the whole chat frontend, feedback, CSV
export, and the PWA/responsive work. (`alembic/` is rebaselined, not kept as-is.)

**Dependency removals follow the moves, not the other way round.**
`tensorflow==2.14.0` comes out of `requirements/default.txt` only after
`model_server/custom_models.py` is moved and CI is green. Same for `dask`,
`celery`, `supervisor`, `nltk`, `llama-index`, `playwright`, and the connector
SDKs. `torch` and `sentence-transformers` **stay** — the embedding worker needs
them.

---

## Database migrations: start a new Alembic baseline

**Decision (overrides the earlier "never touch migrations" rule):** squash the
inherited history into one Heal baseline and move the old chain to
`deprecated/`.

### What is there now

| Fact | Value |
| --- | --- |
| Migration files | **49**, one linear chain, no branches |
| Root | `47433d30de82_create_indexattempt_table.py` (`down_revision = None`) — the history begins with a connector-indexing table |
| Head | **`853cc4ff26b5`** — `enable_chat_translation`, Heal's own, 2024-02-05 |
| Head adds | `chat_message.language` (NOT NULL), `chat_message.luganda_message` (nullable) |
| `env.py:25` | `target_metadata = [Base.metadata, ResultModelBase.metadata]` |

Design A still uses both columns from the head migration, so they must survive.

### The one thing that makes this dangerous

There is a **production database with real user accounts and chat history**. A
new baseline changes what `alembic_version` holds. If the new baseline is run
(rather than stamped) against that database, it will attempt `CREATE TABLE` on
tables that already exist and fail — or worse, partially apply.

The procedure below is safe because it never runs DDL against production.

### Procedure: squash and stamp

```text
 [0] BACKUP FIRST. pg_dump of production, full data, verified restorable.
     This is the only rollback path. Do not start step 1 without it.

 [1] Capture the truth
       pg_dump --schema-only production > baseline_prod.sql
     This is the schema the baseline must reproduce exactly.

 [2] Write the baseline
       backend/alembic/versions/0001_heal_baseline.py
         revision = "0001_heal_baseline"
         down_revision = None
     Generate with autogenerate against an empty database, then hand-review
     every line against baseline_prod.sql.

 [3] Move the old chain
       git mv backend/alembic/versions/*.py
              backend/deprecated/alembic_danswer/versions/
     All 49 files. Move only; no edits.

 [4] Fix env.py
       target_metadata imports must point at the live models module, not at
       anything now sitting under deprecated/.

 [5] PRODUCTION: stamp, do not upgrade
       alembic stamp 0001_heal_baseline
     This writes the new revision id into alembic_version and executes NO DDL.
     The database is untouched; Alembic simply agrees it is up to date.

 [6] FRESH DATABASE: upgrade
       alembic upgrade head
     Creates the whole schema from the baseline.

 [7] THE GATE — this is the acceptance check, not an optional nicety
       pg_dump --schema-only fresh_migrated_db > baseline_fresh.sql
       diff baseline_prod.sql baseline_fresh.sql
     Must diff clean (modulo ordering). If it does not, the baseline is wrong.
     Fix the baseline and repeat. Do not proceed on a dirty diff — a mismatch
     here means production and new deployments silently diverge, and you will
     not find out until something breaks in the pilot.
```

### The mistake to avoid

**The baseline must be a faithful snapshot of the schema as it exists today —
including every table you are about to deprecate.** `index_attempt`,
`connector`, `credential`, `connector_credential_pair`, `document_set`,
`slack_bot_config`, `user_group`, the tag tables, and the rest all exist in
production right now.

It is tempting to write a "clean" baseline containing only the tables Heal keeps.
Do not. If the baseline omits a table that exists in production, then step [5]
stamps a lie: Alembic believes the database matches the baseline when it does
not, step [7] fails, and every future autogenerate produces nonsense diffs.

**Dropping the retired tables is a separate forward migration** — `0002_drop_*`
— written after the pilot is stable, on evidence that nothing reads them. Not in
these two weeks. Empty tables cost nothing.

### Rules

1. Backup and verify the restore **before** touching anything.
2. `alembic stamp` runs against production exactly once, by one person, with the
   backup confirmed. Write down the command that was run and when.
3. The move of the 49 files is its own commit, moves only, 100% rename
   similarity.
4. Files under `deprecated/alembic_danswer/` are never executed. Remove that path
   from `version_locations` so Alembic cannot discover them.
5. The step [7] schema diff is a CI job, not a one-time manual check.
6. Column-level note: the head migration adds `chat_message.language` as
   NOT NULL with no server default (`853cc4ff26b5`). That only succeeds on an
   empty table. Reproduce whatever production actually has — check whether the
   live column carries a default before writing the baseline.

---

## Language: translate-then-retrieve (D2)

```text
   Luganda query
        |
        v
   LanguageService.to_english()      OpenAI Responses API
        |
        v
   English query  --------> English embedding --------> Qdrant (English chunks)
        |                                                    |
        v                                                    v
   English answer  <---- OpenAI Responses (+ English context, citations)
        |
        v
   LanguageService.to_luganda()
        |
        v
   Luganda answer  +  citations rendered from PostgreSQL source metadata
```

**Why A and not B.** `multilingual-e5-*` and `BAAI/bge-m3` are both built on
XLM-RoBERTa, whose pretraining language list does not appear to include Luganda.
Climbing that ladder buys coverage of languages Heal does not serve. Direct
Luganda embedding (Design B) would mean AfroXLMR-family encoders fine-tuned for
retrieval — a research project, not a two-week MVP. **Verify the XLM-R language
list on the model cards before anyone re-opens this.**

Consequences to hold onto:

- The knowledge corpus is stored and embedded in **English**. If a source arrives
  in Luganda, it is translated at ingest and both versions are kept in
  PostgreSQL — the English one is what gets embedded.
- Translation quality is now on the critical path for clinical safety. It needs
  its own English↔Luganda medical-phrase test set covering drug names, dosage
  units, negation, and uncertainty, run before rollout and in CI after.
- Citations are rendered from PostgreSQL metadata, so a Luganda user sees
  Luganda answer text with English source titles. Decide the display convention
  before the pilot; do not machine-translate source titles.

---

## Embedding compute: run the lightest thing that is ready (D6)

Because retrieval is English-only, the embedding model does not need to be
multilingual at all. That removes the hardest constraint. Keep **384 dimensions**
so the existing shape, config, and any earlier index work stay valid.

Candidates that are ready today — no training, no new infrastructure:

| Model | Dim | Size | Status in this repo | Note |
| --- | --- | --- | --- | --- |
| `thenlper/gte-small` | 384 | ~33M | **already the default** (`model_configs.py:14`) | zero-work baseline; measure it first |
| `BAAI/bge-small-en-v1.5` | 384 | ~33M | not wired | generally the stronger English retriever; needs `ASYM_QUERY_PREFIX` handling |
| `intfloat/e5-small-v2` | 384 | ~33M | prefix vars already exist in `env.multilingual.template` | asymmetric `query:`/`passage:` prefixes already plumbed |
| `intfloat/multilingual-e5-small` | 384 | ~118M | in `env.multilingual.template` | only if Design A is ever reversed; 3.5x the weight for no English gain |

**Procedure:** start on `gte-small` because it costs nothing to keep. Build the
clinician eval set. Swap to `bge-small-en-v1.5` or `e5-small-v2` only if
Recall@5 fails, and only on measured evidence. All three are 384-dim, so a swap
is a re-embed of the same collection, not a schema change.

**Verify licences before shipping.** The repo's own rule is "MIT or Apache"
(`model_configs.py:9`). Check each candidate's card. `jinaai/jina-embeddings-v3`
is an obvious mid-size multilingual candidate and is **CC-BY-NC** — it fails this
rule; do not use it.

**No reranker at launch** — see *Ranking and reranking* below for the full
argument and the trigger to add one. Note that Design A changes this question:
because translation happens upstream, a reranker would receive an English query,
so the existing English cross-encoders are no longer disqualified on language
grounds. They are deferred on latency, cost, and lack of clinical validation.

**Where it runs.** One `embedding_worker` module inside `heal/knowledge/`,
invoked on-demand by the ingest job. Not a permanent server, not two servers, no
warm-up daemon. Phase 1 does not run it at all.

---

## Ranking and reranking — where it went

This is the part of the old system with the most machinery and the least
documentation, so it is spelled out here rather than left implicit in the
diagram.

### What ranks results today (six stages)

```text
  query
    |
 [1] doc_index_retrieval()                    search_runner.py:140
       KEYWORD | SEMANTIC | HYBRID  -> Vespa
       HYBRID_ALPHA blends BM25 + vector
       time_decay_multiplier applies recency bias
    |
 [2] combine_retrieval_results()              search_runner.py:115
       dedupe by key, keep max score, re-sort
    |
 [3] semantic_reranking()                     search_runner.py:178
       2x English MS MARCO cross-encoders     model_configs.py:45-47
       ensemble average -> min-shift
       x boosts  x recency_multiplier -> normalize -> sort
    |     (if reranking is off, apply_boost_legacy() at :247 instead)
    |
 [4] chunk.boost                              document_index_utils.py:11
       admin/crowd document feedback -> integer
       sigmoid curve -> 0.5x .. 2.0x score multiplier
    |
 [5] filter_chunks()  LLM relevance filter    full_chunk_search_generator:540
       one more LLM round trip; yields list[bool]
    |
 [6] map_document_id_order()                  chat_utils
       fixes citation numbering from final order
    |
  chunks fed to the LLM
```

### What ranks results in the new flow

```text
  english query
    |
 [1] PRE-filter in Qdrant   (payload filter, applied before ANN search)
       approved == true  AND  source_version is current
       Must be a Qdrant filter, NOT a post-search drop. Post-filtering an
       HNSW result set silently returns fewer than k and hides the loss.
    |
 [2] vector similarity ordering            <-- THIS IS THE PRIMARY RANK
       cosine score from Qdrant, descending. One model, one collection.
    |
 [3] SCORE FLOOR                           <-- new; the old system had none
       below MIN_RETRIEVAL_SCORE -> return nothing
       the agent then says "no approved source", it does not guess
    |
 [4] per-source diversity cap
       max N chunks per source document, so one guideline cannot crowd out
       a second corroborating source
    |
 [5] clinician boost   [phase 2.5, optional]
       admin-set, audited, per source_version. NOT crowd-voted.
    |
 [6] context ordering + citation numbering
       final order determines position in the prompt and citation numbers
    |
  chunks -> PromptBuilder
```

### Stage-by-stage: kept, replaced, or dropped

| Old stage | Status | Reasoning |
| --- | --- | --- |
| Hybrid BM25 + vector (`HYBRID_ALPHA`) | **dropped — biggest real loss** | Went with Vespa. See *Ranking risk* below; this is the one to watch. |
| Keyword / semantic mode switch | dropped | One collection, one model. Nothing to switch between. `SearchType` has no meaning. |
| Recency decay (`time_decay_multiplier`) | **replaced, and improved** | A curated library of approved clinical guidance should not silently prefer newer text. Supersession is explicit: a `source_version` is approved or it is not. Explicit beats decay for clinical documents. |
| Cross-encoder reranking | deferred, not forbidden | See *When to add a reranker*. |
| Crowd/admin `boost` sigmoid (0.5x–2.0x) | replaced by clinician boost | An unaudited multiplier that silently reweights clinical sources is the wrong control. The replacement is admin-set, versioned, and logged. |
| LLM relevance filter | dropped | One extra LLM round trip per query. The score floor does the cheap 80% of this job with no latency. |
| Citation ordering | kept | Still needed, same job. |
| — | **score floor is new** | The old pipeline always returned top-k regardless of quality. For `DOSAGE_OR_MEDICATION`, citing a weak match is worse than refusing. |

### Ranking risk #1: lexical matching

Pure dense retrieval is weakest exactly where this product is most sensitive:
drug codes, abbreviations and dosages — `TDF/3TC/DTG`, `500mg BD`, ICD codes.
BM25 handled these in the old stack for free, and dropping Vespa drops it.

**Mitigation, in order:** measure it on the eval set first (build cases
deliberately around codes and abbreviations); if it fails, add **Qdrant sparse
vectors** for hybrid dense+lexical search. That is a Qdrant feature, not a new
service, and it is the cheap answer to BGE-M3 use case #4.

Do not treat this as theoretical. Write the drug-code eval cases in Day 9.

### When to add a reranker

**Correction to an earlier version of this plan.** The objection that the
existing cross-encoders are "English-only and unvalidated for Luganda" **no
longer applies under Design A** — the query reaching a reranker is already
English, because translation happens upstream. `cross-encoder/ms-marco-MiniLM-L-4-v2`
is therefore a usable candidate, which it would not have been under Design B.

The remaining objections are real but narrower:

1. It scores query/chunk pairs one at a time — latency and CPU grow with `k`.
2. It is trained on MS MARCO web text, not clinical guidance. Unvalidated here.
3. At 100 documents and a few thousand chunks, the retrieval candidate set is
   small enough that reranking has little room to help.

**Trigger to add one:** the eval set shows the correct chunk is retrieved inside
the top 20 but not inside the top 5. That is precisely the reranker-shaped
failure. If the correct chunk is not in the top 20 at all, a reranker cannot fix
it — that is a chunking, translation, or source-coverage problem, and reranking
would only hide it.

**Not at launch.** `ENABLE_RERANKING_REAL_TIME_FLOW` stays `false`.

### Constants to pick before first ingest

| Constant | Purpose | Note |
| --- | --- | --- |
| `RETRIEVAL_TOP_K` | candidates fetched from Qdrant | start 20 |
| `CONTEXT_TOP_K` | chunks passed to the prompt | start 5 |
| `MIN_RETRIEVAL_SCORE` | score floor | **must be tuned on the eval set, not guessed** — it is a clinical-safety parameter |
| `MAX_CHUNKS_PER_SOURCE` | diversity cap | start 2 |

`MIN_RETRIEVAL_SCORE` is the one that matters. Too low and the agent cites
irrelevant text with a citation that lends it false authority; too high and it
refuses questions it could have answered. Set it from measured data on Day 9 and
record the value and the evidence in this repo.

---

## Admin surface

The admin area is currently 12 route groups, most of which exist to operate the
connector and indexing fleet. Noting it here because two of its screens are
**ranking controls**, not just views — retiring them without a replacement
silently changes retrieval behaviour.

### What is there now

| Route | Backend | Decision |
| --- | --- | --- |
| `admin/connectors/*` (~20 providers), `admin/connector/[ccPairId]`, `admin/add-connector` | `server/documents/connector.py`, `credential.py`, `cc_pair.py` | move — no connectors in the MVP |
| `admin/indexing/status` | `server/documents/` | move — no background indexing |
| `admin/documents/explorer` | `server/documents/document.py` | **replace** — becomes the approved-source browser |
| `admin/documents/feedback` | `server/documents/document.py` → `chunk.boost` | **replace, do not just drop** — this is a live ranking control (see below) |
| `admin/documents/sets` | `server/features/document_set/` | move — one approved library, no sets |
| `admin/personas` (+ `new`, `[personaId]`) | `server/features/persona/`, `prompt/` | move — D3 fixes one agent |
| `admin/bot` (+ `new`, `[id]`) | `server/manage/slack_bot.py` | move — Slack bot retired |
| `admin/keys/openai` | `server/manage/` | **keep** — still need the OpenAI key |
| `admin/users` | `server/manage/users.py` | **keep** |
| `admin/sessions` | `server/query_and_chat/` | **keep** — Heal-added, serves the feedback loop |
| `admin/systeminfo` | `server/manage/get_state.py` | **keep** — becomes the health/jobs view |

### The one that is easy to get wrong

`admin/documents/feedback` is not a report. It writes an integer `boost` per
document (`db/document.py:152,173`), which `translate_boost_count_to_multiplier`
(`document_index_utils.py:11-21`) turns into a **0.5x to 2.0x multiplier on the
retrieval score** via a sigmoid, applied in `semantic_reranking`
(`search_runner.py:204-206`). Moving that screen to `deprecated/` removes a
ranking input.

That is the right outcome — an unaudited crowd multiplier over clinical sources
is a control Heal should not have — but it must be a **decision, not an
accident**. Its replacement is stage [5] of the new pipeline: an admin-set,
versioned, logged clinician boost, added in phase 2.5 only if the eval set shows
it is needed.

### Admin for the MVP

```text
Phase 1
  admin/users          accounts and roles
  admin/sessions       chat sessions
  admin/feedback       NEW - answer feedback review + export   <- serves the
                       clinical review loop the product depends on
  admin/systeminfo     health, versions, config
  admin/keys           OpenAI key

Phase 2 adds
  admin/sources        approved medical sources: upload, approve, version,
                       supersede, re-embed. Replaces documents/explorer.
  admin/jobs           reference_ingest runs: queued/started/completed/failed,
                       counts, model version, source version, actor, time.
                       No patient text.
```

`admin/feedback` is the highest-value new admin screen and the smallest. The
plan already commits to a clinician-reviewed evaluation and feedback loop; that
loop needs a place to read from. It is Week 2 work and it should not be cut.


---

## When a smaller-scale BGE-M3 actually earns its weight

`BAAI/bge-m3` is a retrieval model, not a chat model or an agent: it turns
queries and chunks into comparable representations. It is 1024-dim, 8192-token,
roughly 2.3 GB. Under Design A it is **not needed at launch**. These are the
concrete conditions that would justify it — and the lighter thing to try first
in each case.

| # | Use case | Why BGE-M3 fits | Try this first |
| --- | --- | --- | --- |
| 1 | **Luganda source documents must be ingested as-is** — a partner supplies Luganda-only protocols that cannot be translated at ingest | multilingual encoder; removes the translation hop from the corpus side | translate at ingest, keep both versions in PostgreSQL (Design A already covers this) |
| 2 | **Cross-lingual retrieval without a translation hop** — Design A is reversed and a Luganda query must hit an English chunk directly | trained for cross-lingual alignment | `multilingual-e5-base` (768d, ~278M) — the genuine "smaller-scale BGE-M3" |
| 3 | **Long clinical documents where 512-token chunks destroy meaning** — national treatment guidelines where a dosage clause depends on a table three pages earlier | 8192-token context keeps the clause and its qualifier in one vector | parent-document retrieval: embed small chunks, return the enclosing section. Cheaper and usually better |
| 4 | **Drug names, dosages, and ICD codes must match lexically *and* semantically** — "TDF/3TC/DTG" or "500mg BD" must hit exactly | emits dense + sparse lexical weights + multi-vectors from one model | Qdrant sparse vectors / BM25 alongside the small dense model — hybrid without a 2.3 GB model |
| 5 | **Measured recall failure isolated to the embedding** — eval set shows Recall@5 failing, and chunking, translation, and source coverage have each been ruled out | genuinely stronger retriever | re-chunk, then `bge-small-en-v1.5`, then `multilingual-e5-base`, in that order |
| 6 | **Corpus grows past a few thousand documents with heavy domain vocabulary** | capacity to separate near-duplicate clinical text | not yet a real Heal condition at 100 documents |

**Do not adopt it for any of these reasons:** it sounds stronger; it is newer;
another project uses it; it is "more multilingual". Adoption requires a measured
gain on the same held-out clinician set, run offline, against the incumbent.

**Cost if adopted:** 1024 dims is a new Qdrant collection and a full re-embed
(~2.7x the vector storage), a much slower ingest, and a materially larger
container image. That is why D6 freezes the dimension before first ingest.

---

## Intent: keep it, with a medical label set (D4)

### What is being retired and why

| Fact | Location |
| --- | --- |
| `INTENT_MODEL_VERSION = "danswer/intent-model"` | `configs/model_configs.py:61` |
| It is a `TFDistilBertForSequenceClassification` | `search/search_nlp_models.py:40,92` |
| It is the only reason TensorFlow is a dependency | `model_server/custom_models.py:2` |
| Its classes are keyword / semantic / QA | `search/danswer_helper.py:25-30` |
| Its output is a `SearchType` + a `QueryFlow` | same |
| Consumed only here | `search/request_preprocessing.py:101-126`, `server/query_and_chat/query_backend.py:106` |
| Max context 256 tokens, English DistilBERT | `configs/model_configs.py:58` |

Its entire output feeds one decision: *should Vespa run keyword or semantic
search, and should the UI show a result list or an answer.* With one Qdrant
collection and one embedding model, that branch does not exist. `QueryFlow.SEARCH`
is also dead once the search page is retired. And a Luganda query through an
English DistilBERT is noise.

Note for the record: `check_if_need_search` (`chat/process_message.py:263`) is
**not a model** — it is an LLM prompt in `secondary_llm_flows/choose_search.py`.
It folds into the intent call. That is a merge, not a deletion.

### What replaces it

```text
heal/medical_guidance/intent.py

  MedicalIntent
    EMERGENCY              escalation copy first, then answer
    DOSAGE_OR_MEDICATION   citation REQUIRED; refuse if no approved source
    CLINICAL_QUESTION      retrieve + cite
    GENERAL_HEALTH_INFO    retrieve if available
    ADMIN_OR_SMALLTALK     no retrieval, no citation
    OUT_OF_SCOPE           decline + redirect

  Implementation: structured output on the OpenAI Responses call.
  Input: English query (post-translation) + short history.
  No TensorFlow. No model server. No local weights. Works in both
  languages because translation happens upstream.

  Every classification writes an audit event: intent, confidence,
  route taken, model version. No patient text in the event.
```

This is the mechanism the safety requirement ("emergency escalation") currently
has no implementation for. A small fine-tuned local classifier is a later
optimisation if measured latency or cost demands it — and it belongs in
`medical_guidance/`, not in a model server.

**Route table is fixed and versioned.** The model classifies; it does not choose
what happens next. Changing a route is a code change with review.

---

## The one agent: MedicalGuidanceAgent (D3)

```text
MedicalGuidanceAgent
  fixed, versioned safety instructions
  English + Luganda response mode (via LanguageService)
  MedicalIntent routing (fixed table, not model-chosen)
  approved KnowledgeStore retrieval only
  citations required whenever knowledge is used
  actions/tools: none
```

It may retrieve only approved medical references and must cite them. It may never
browse the web, execute code, change a record, or call an external clinical
system. There is no agent selector, planner, tool loop, multi-agent handoff, or
autonomous background task.

Keep the module boundary so future capability is additive: an approved
`FacilityProtocolModule` can be added later without touching the chat core. Any
future tool requires an allowlist, an authenticated server-side handler,
structured input/output, consent where applicable, an audit event, a failure
message, and a human-review design before it is enabled.

This works without importing Onyx. It is one policy module plus a
`KnowledgeStore` interface — not a general-purpose agent runtime.

---

## Chat refactor: borrow Onyx's seams, not its loop

`stream_chat_message` is a 543-line function (`chat/process_message.py:151-543`)
with ten inline branches. The Jan-2025 Onyx snapshot at
`~/Desktop/dexta_s_lab/onyx-teacher` split the same job into named seams. Take
three of them; refuse the rest.

| Heal today | Onyx equivalent | Take it? |
| --- | --- | --- |
| inline prompt assembly in `process_message` | `chat/prompt_builder/` (186 + 180 lines) | **Yes** — system + history + context becomes testable |
| citations parsed mid-stream | `chat/stream_processing/` | **Yes** — decouples citation extraction from the token stream |
| the 543-line function | `chat/answer.py` — `Answer` orchestrator (309 lines) | **Yes, shape only** — an orchestrator that calls steps and holds none |
| `check_if_need_search` + `retrieval_preprocessing` | `SearchTool` in `tools/tool_implementations/search/` | **No** — call `KnowledgeStore` directly; do not wrap it as a Tool |
| — | `tools/tool_selection.py`, `tool_runner.py`, `force.py` | **No** — this is the model-picks-its-own-action loop D3 rules out |
| — | `InternetSearchTool`, `ImageGenerationTool`, `CustomTool` | **No** |

The distinction that matters: Onyx's `Answer._get_response(llm_calls)` is a loop
in which the model chooses tools. `MedicalGuidanceAgent` is a straight line that
happens to reuse Onyx's prompt-building and stream-processing shapes. Testability
without autonomy.

Also do not copy from that checkout: Vespa, Redis, the two model servers
(inference + indexing), the Supervisor/Celery queue set, Celery Beat, the
connector fleet, and the Slack bot.

---

## What used to run in the background

The `background` service (`docker-compose.dev.yml:80`, and
`deployment/kubernetes/background-deployment.yaml`) is a **second full copy of
the backend image** whose command is `/usr/bin/supervisord`. Supervisor starts
five long-lived programs (`backend/supervisord.conf`).

```text
  background container  =  danswer/danswer-backend:latest  +  supervisord
    |
    |-- [1] document_indexing
    |     python danswer/background/update.py :: update_loop(delay=10)
    |     CURRENT_PROCESS_IS_AN_INDEXING_JOB=true
    |
    |     while True:                              <- forever, every 10s
    |         cleanup_indexing_jobs()
    |         create_indexing_jobs()                <- polls every connector
    |         kickoff_indexing_jobs(client)
    |         sleep(10 - elapsed)
    |
    |     client = Dask LocalCluster(n_workers=NUM_INDEXING_WORKERS,
    |                                threads_per_worker=1)
    |              or SimpleJobClient if DASK_JOB_CLIENT_ENABLED=false
    |     each worker process loads torch + the embedding model into RAM
    |     each job: connector pull -> chunk -> embed -> write Vespa
    |               + checkpointing.py, run_indexing.py, dask_utils.py
    |
    |-- [2] celery_worker
    |     celery -A danswer.background.celery worker
    |            --pool=threads --autoscale=3,10
    |     tasks:  cleanup_connector_credential_pair_task   (:53)
    |             sync_document_set_task                   (:91)
    |             check_for_document_sets_sync_task        (:172)
    |             clean_old_temp_files_task                (:203)
    |     threads pool, not prefork — a documented workaround for a
    |     Celery + SQLAlchemy SIGSEGV bug (celery/celery#7007)
    |
    |-- [3] celery_beat                              celery.py:221
    |     check-for-document-set-sync   every 5 SECONDS
    |     clean-old-temp-files          every 30 minutes
    |
    |-- [4] slack_bot_listener
    |     python danswer/danswerbot/slack/listener.py
    |     startretries=5, startsecs=60 — if Slack is not configured it
    |     fails five times and stays dead, logging as it goes
    |
    '-- [5] log-redirect-handler
          tail -qF over six log files -> stdout
```

Plus `background/connector_deletion.py`, which exists purely to keep document
deletions consistent between PostgreSQL and Vespa.

### What that costs Heal today

| Observation | Consequence |
| --- | --- |
| Beat polls for document-set sync **every 5 seconds** | ~17,000 database round trips a day. Heal has no document sets, so every one of them finds nothing. |
| The indexing loop runs **every 10 seconds, forever** | ~8,600 iterations a day polling connectors Heal has not configured. |
| Dask spawns N worker processes, each loading torch + the embedding model | This, not Vespa, is usually the largest resident-memory line in the deployment. |
| The container carries `GEN_AI_API_KEY` (`docker-compose.dev.yml:95`) | The OpenAI key is mounted into a service Heal does not use, purely because DanswerBot once needed it. Reducing key blast radius is a security win on its own. |
| The Slack listener is almost certainly dead in Heal's deployment | Five failed starts, then silence. Noise in the logs, zero function. |
| Supervisor + Celery + Beat + Dask are **four** process supervisors | Four failure modes, four log formats, and a documented SIGSEGV workaround, to run jobs Heal does not have. |

None of this serves a health worker asking a question. All five programs exist to
feed Vespa from external connectors.

### What replaces it

**Phase 1: nothing.** The `background` container is not deployed. A request comes
in, an answer streams out, rows are written. There is no scheduler, no queue, no
worker pool, and no supervisor. This is the single largest simplification in the
plan and it costs no functionality Heal actually uses.

**Phase 2: one job, triggered by a person.**

```text
  reference_ingest(source_file, actor)          heal/knowledge/
    validate upload
    extract text
    chunk
    embed            <- embedding_worker, loaded for the job, released after
    write PostgreSQL source + source_version + chunk rows
    write Qdrant points
    record job result
```

Run it in-process on the API worker for the first release, or in a single
`arq`/`RQ`-style queue if ingest of a large PDF blocks a request for too long.
**Do not reach for Celery + Beat + a broker for one on-demand job.** Measure
first: at 100 documents, ingest is a rare administrative action, not a workload.

Rules that keep it from growing back into the fleet:

1. **No scheduler.** Nothing is time-triggered. Every run has a human actor
   recorded against it.
2. **One writer.** `reference_ingest` is the only code that writes Qdrant.
3. **PostgreSQL first, Qdrant second.** Postgres is the system of record, so it
   commits first; Qdrant points are written after and are reconstructible from it.
4. **Reconciliation, not sync.** The old `connector_deletion.py` problem does not
   fully disappear — two stores can still drift. Replace continuous sync with a
   cheap admin-triggered reconcile that compares PostgreSQL chunk rows against
   Qdrant point ids and reports the difference. Report, do not auto-repair.
5. **Every run writes an immutable event**: `queued`, `started`, `completed`,
   `failed`, counts, model version, source version, actor, timestamp.
   **No patient text in the event record.**
6. Visible in `admin/jobs`. A background job nobody can see is the thing this
   plan is removing.

---

## Background work policy going forward

| Stage | Allowed background work | Explicitly not running |
| --- | --- | --- |
| Phase 1 — chat-only | **None.** Requests stream replies and write chat/feedback rows. | Vespa, Celery, Beat, Dask, Supervisor, Slack listener, connector polling, model server |
| Phase 2 — curated reference | One on-demand `reference_ingest` job: validate upload → extract text → chunk → embed → write PostgreSQL rows + Qdrant points → record job result | Periodic crawling, connector sync, model warm-up, automatic re-index without an administrator action |
| Later | A separate, named connector job only after approval; schedule, documents processed, failures and last successful run shown in the admin UI | Hidden background agents with authority to alter clinical data or call external systems |

Each job writes an immutable operational event (`queued`, `started`, `completed`,
`failed`, counts, model version, source version, actor, time). **No patient text
in the event record.**

---

## Two-week plan to pilot (2026-08-26 → 2026-09-09)

The deadline is real, so the cut line is stated in advance: **Phase 1 ships on
Day 10 whether or not Phase 2 is ready.** Knowledge/Qdrant is the part that gets
cut, not the safety work and not the testing.

### Week 1 — make it work without Vespa

| Day | Work | Done when |
| --- | --- | --- |
| 1 | Branch `simplify/phase-1`. Create the `deprecated/` trees + `docs/deprecated/MOVED.md` + the CI grep gate. **Back up the production PostgreSQL database and verify the restore.** Capture `pg_dump --schema-only`. | Gate fails on a deliberate test import; a restored copy of production runs locally |
| 1–2 | **Alembic rebaseline:** write `0001_heal_baseline`, move the 49 old files, fix `env.py`, stamp production, upgrade a fresh DB. | The step [7] schema diff is clean and running as CI |
| 2 | `heal/language/LanguageService` on OpenAI Responses. Upgrade `openai==1.3.5`. Move `utils/translation.py`. Timeouts, retries, user-safe error, no content logged. | English↔Luganda medical-phrase tests pass |
| 3–4 | Chat-only flow: `MedicalGuidanceAgent` skeleton + `PromptBuilder` + `StreamProcessor`. Build messages from stored history + safety instruction. Retrieval bypassed. **UI API contract unchanged.** | Streaming, sessions, feedback, CSV export all work in both languages |
| 5 | `MedicalIntent` + fixed route table + audit events. Retire `query_intent`, `check_if_need_search`, rephrase, chunk filter. | Emergency and out-of-scope cases route correctly on a written test set |
| 6 | Move Vespa, indexing, search, connectors, background, bot, model_server, search UI. Reduce compose to api + web + postgres. Drop `tensorflow` and friends **after** CI is green. | `grep -rniE "vespa|VESPA_|VespaIndex" backend/heal web/src deployment` returns no live reference |

### Week 2 — make it safe, then ship

| Day | Work | Done when |
| --- | --- | --- |
| 7 | Fresh-environment rebuild from the reduced compose. Verify login, new chat, streaming, rename/delete, export, feedback, both languages, on mobile. | A clean machine reaches a working chat |
| 8 | **Go/no-go on Phase 2.** Qdrant up, ARM64 + auth + snapshot/restore verified. `KnowledgeStore` interface + `reference_ingest` job + `embedding_worker` on `gte-small`. | 100-document test collection ingested, or Phase 2 formally cut |
| 9 | Clinician eval set: Recall@5, citation correctness, emergency and unsafe-answer cases, English and Luganda. **Include deliberate drug-code / dosage / abbreviation cases** (ranking risk #1) and **tune `MIN_RETRIEVAL_SCORE` from the results — do not guess it.** Rate limits, cost caps, structured error logging. | Eval results and the chosen score floor written into this repo, signed off by a clinician |
| 10 | Load-smoke realistic concurrent streams (target 20–50 simultaneous chats). README corrected. Release behind a small pilot. | Pilot live with a documented rollback |

**Not in these two weeks, deliberately:** the Danswer→Heal package rename, any
`deprecated/` deletion, any **table-drop** migration (the rebaseline happens;
dropping retired tables does not), connectors, rerankers, BGE-M3, Capacitor
native shell releases, and Kubernetes. The rename is the final
cleanup after the pilot is stable — doing it now would make every removal review
unreadable and risk breaking migrations that are about to be retired anyway.

### Refactor discipline — non-negotiable under this deadline

1. **One concern per PR.** A move commit contains only moves. A behaviour commit
   contains only behaviour.
2. **The frontend API contract does not change in Week 1.** The UI keeps calling
   the same endpoints with the same payloads. Frontend cleanup is Week 2 or later.
3. **No schema drops.** Unused columns and tables stay. `language` and
   `luganda_message` on `ChatMessage` are still used by Design A.
4. **Every day ends on a green CI and a deployable branch.** If a day's work is
   not green, it is reverted, not carried.
5. **Feature-flag the retrieval path.** `KNOWLEDGE_ENABLED=false` must produce
   the exact Phase 1 behaviour, so Day 8 can be cut without a rollback.
6. **Nothing ships without the safety instruction and the emergency route.**
   These are the reason the product exists; they are not a Week-2 nice-to-have.

---

## Capacity targets

| Target | Initial approach |
| --- | --- |
| 100 approved documents / a few thousand chunks | One Qdrant node, one PostgreSQL node, one embedding worker. No cluster, no replica. ~2,000 × 384 × 4 bytes ≈ 3 MiB of raw vectors. |
| 700 registered or daily users | Same topology; rate-limit and monitor chat/API usage. |
| 20–50 simultaneous chats | Multiple stateless API workers, connection pooling, streaming limits, OpenAI rate-limit budget, load testing. **This is the Day 10 target.** |
| 700 simultaneous chats | A separate scaling exercise: scale API workers horizontally, queue ingest separately, size provider limits, load-test p95, add Qdrant replicas only if measured search latency requires it. |

The first bottlenecks will be LLM latency and rate limits, streaming worker
capacity, and database connections — not vector search over a few thousand
chunks. Retrieval quality comes from approved sources, chunk boundaries,
translation quality, and the clinical evaluation set, not from a bigger database.

Qdrant's default local setup has **no authentication**. Its container must be
private and authenticated in any real deployment.

---

## Findings that need attention regardless of scope

- Dependencies are not installed locally, so no build or automated test has been
  run in this review. Day 1 should establish a green baseline before anything
  moves.
- The fork is a January 2024 upstream snapshot plus Heal changes. Treat it as a
  migration, not a version upgrade.
- `utils/translation.py` uses plain HTTP to hard-coded public IPs
  (`65.108.33.93:4002` and `:5000`) with no timeout and no failure fallback.
  This is the single highest-priority replacement — reliability and privacy both.
- `README.md` currently promises private-source answers. It must be corrected
  when Phase 1 removes retrieval, and corrected again if Phase 2 restores it.
- `GEN_AI_MODEL_VERSION` defaults to `gpt-3.5-turbo` and `openai==1.3.5` is from
  2023. Model choice must be tested on the English/Luganda medical eval set, not
  chosen by name.
- The reference link below to the Onyx repository looks wrong and should be
  checked — Onyx appears to live at `onyx-dot-app/onyx`.

## Reference material

- [OpenAI Responses API reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [OpenAI embeddings API reference](https://developers.openai.com/api/reference/ruby/resources/embeddings/methods/create)
- [Qdrant installation](https://qdrant.tech/documentation/installation/)
- [Qdrant security](https://qdrant.tech/documentation/security/)
- [BAAI/bge-m3 model card](https://huggingface.co/BAAI/bge-m3)
- [Onyx (successor to Danswer)](https://github.com/danswer-ai/danswerai) — verify this URL
