# Heal runtime architecture: what actually runs

**Revised:** 2026-08-28
**Companion to:** `docs/keep-and-simplify-plan.md`

The plan describes the **destination**. This document describes **what is
running on any given day between here and there**, service by service, with the
code that keeps each one alive.

If you are looking at `docker-compose.dev.yml` and wondering why Vespa is still
there, the short answer is in *Stage 0* and the removal order is in
*Why Vespa is still running*.

---

## The four stages

Services are removed in a specific order because most of them are held in place
by code, not by configuration. Deleting a container before deleting its caller
produces a service that will not boot.

| Stage | When | Services | Compose file |
| --- | --- | --- | --- |
| **0 — inherited** | today, unchanged from the fork | 7 | `docker-compose.dev.yml` |
| **1 — local** | today, what you develop against | 5 | `docker-compose.local.yml` |
| **2 — Phase 1 target** | Day 6 of the plan | 3 | `docker-compose.local.yml`, reduced |
| **3 — Phase 2 target** | Day 8, if not cut | 5 | + qdrant, + embedding worker |

---

## Stage 0 — what the fork gives you

`docker-compose.dev.yml`. Seven services, of which two do nothing for a health
worker asking a question.

| Service | Image | Ports | Why it exists | Keep? |
| --- | --- | --- | --- | --- |
| `api_server` | `danswer-backend` | 8080 | FastAPI: chat, auth, feedback, export | **keep** |
| `web_server` | `danswer-web-server` | — | Next.js 14 UI | **keep** |
| `relational_db` | `postgres:15.2-alpine` | 5432 | System of record | **keep** |
| `nginx` | `nginx:1.23.4-alpine` | 80, 3000 | Reverse proxy, TLS termination | **keep** |
| `index` | `vespaengine/vespa:8.277.17` | 19071, 8081 | Hybrid search engine | **retire, Day 6** |
| `background` | `danswer-backend` + supervisord | — | Five long-lived programs, below | **retire, Day 6** |
| `model_server` | `danswer-model-server` | — | Embedding + intent models, off by default (`--profile model-server`) | **retire, Day 6** |

### What `background` is

A **second full copy of the backend image** whose command is
`/usr/bin/supervisord`. `backend/supervisord.conf` starts five programs:

| Program | What it does | Value to Heal |
| --- | --- | --- |
| `document_indexing` | `update_loop(delay=10)` — polls every connector, forever | none: Heal configures no connectors |
| `celery_worker` | connector cleanup, document-set sync | none: Heal has no document sets |
| `celery_beat` | fires document-set sync **every 5 seconds** | none: ~17,000 empty round trips a day |
| `slack_bot_listener` | Slack bot | none: retired |
| `log-redirect-handler` | `tail -qF` over six log files | none once the above are gone |

It also carries `GEN_AI_API_KEY`, so the OpenAI key is mounted into a container
Heal does not use. Removing it is a security win on its own.

---

## Stage 1 — what you run locally today

`docker-compose.local.yml`, via `make up`. This is Stage 0 minus `background`
and `model_server` — the two that cost resources and return nothing.

```text
  browser :3000
      |
      v
  nginx ──┬─> web_server        Next.js UI
          └─> api_server :8080  FastAPI
                  |
                  ├─> relational_db :5432   PostgreSQL — system of record
                  |
                  ├─> index :8081           Vespa — still required to BOOT
                  |                         (see below; not a design choice)
                  |
                  └─> TRANSLATION_EN_URL    private MT, Luganda -> English
                      TRANSLATION_LUG_URL   private MT, English -> Luganda
                      (env-configured, outside the compose)
```

The translation services are **not** compose services. They run outside this
stack and are reached over the network via `TRANSLATION_EN_URL` and
`TRANSLATION_LUG_URL`. Leave them unset and Luganda chat fails with
`TranslationNotConfigured` naming the variable; English chat is unaffected.

---

## Why Vespa is still running

**Not a change of plan.** Vespa is retired at Day 6 of the two-week schedule.
It is still in Stage 1 because it is held in place by code, and the code that
replaces it (the chat-only flow) is Days 3–4.

The single hard blocker is the boot path:

```text
danswer/main.py:281
    get_default_document_index().ensure_indices_exist()
        -> danswer/document_index/factory.py
             return VespaIndex()          # "Currently only supporting Vespa"
```

That runs inside `@application.on_event("startup")`. Remove the `index`
container today and `api_server` does not start — it is not a degraded mode,
it is a crash on boot.

`startup_event` also does three other things worth knowing about, because they
are why a cold start is slow:

- `warm_up_models()` — loads the embedding model and the TensorFlow intent
  model into the API process
- `nltk.download(...)` — stopwords, wordnet, punkt on every boot
- `create_initial_default_connector()` / `associate_default_cc_pair()` — seeds
  connector rows Heal never uses

### Every live caller of the Vespa entry point

`get_default_document_index()` resolves to `VespaIndex` with no other
implementation. These are all of its live callers:

| Caller | Purpose | Fate |
| --- | --- | --- |
| `main.py:281` | `ensure_indices_exist()` on boot | **the hard blocker** — removed with the chat-only flow |
| `chat/process_message.py:42` | retrieval inside `stream_chat_message` | replaced by `KnowledgeStore` (Phase 2) or bypassed (Phase 1) |
| `server/query_and_chat/chat_backend.py:240` | `/document-search-feedback` → `chunk.boost` | retired with the boost mechanism |
| `server/query_and_chat/query_backend.py:15,16` | search page backend | retired with the search UI |
| `server/documents/document.py:10` | connector/document admin | retired |
| `server/manage/administrative.py:21` | admin document controls | retired |
| `server/gpts/api.py:10` | GPTs integration | retired |
| `utils/acl.py:10-12` | source-level ACL sync | retired |
| `one_shot_answer/answer_question.py:25` | search-page answer path | retired |
| `indexing/indexing_pipeline.py:22-24` | connector indexing | retired |
| `background/celery/celery.py:31-33`, `background/connector_deletion.py:34` | background fleet | already out of Stage 1 |

**Confirmed safe:** `create_chat_message_feedback` (`db/feedback.py:143`) — the
answer feedback Heal keeps — is **pure PostgreSQL** and takes no
`document_index`. Only `create_doc_retrieval_feedback` (document search
feedback, being retired) needs Vespa. Answer feedback survives Vespa's removal
untouched.

### Removal order

Vespa cannot come out first. The sequence is:

```text
 [1] Days 3-4  chat-only flow: MedicalGuidanceAgent + PromptBuilder +
               StreamProcessor. Retrieval bypassed behind KNOWLEDGE_ENABLED.
 [2] Day 5     MedicalIntent replaces query_intent + check_if_need_search,
               which removes the TensorFlow intent model from the boot path.
 [3] Day 6     strip startup_event: no ensure_indices_exist, no warm_up_models,
               no nltk download, no default connector seeding.
 [4] Day 6     move the retiring callers above to deprecated/.
 [5] Day 6     delete the `index` service. Stage 2 reached.
```

Step [5] is last, and it is the cheap one. Steps [1]–[4] are the work.

---

## Stage 2 — Phase 1 target (Day 6)

Three services. **No background process of any kind.** A request comes in, an
answer streams out, rows are written, nothing else runs.

```text
  browser :3000
      |
      v
  nginx ──┬─> web_server
          └─> api_server ──> relational_db
                    |
                    └──> translation services (external, env-configured)
                    └──> OpenAI API
```

| Service | Keep | Note |
| --- | --- | --- |
| `api_server` | yes | chat, auth, feedback, CSV export |
| `web_server` | yes | chat UI; search/admin-connector routes retired |
| `relational_db` | yes | system of record |
| `nginx` | yes | may be dropped locally; needed in deployment |

Also gone by this point, from `requirements/default.txt`: `tensorflow`,
`dask`, `celery`, `supervisor`, `nltk`, `llama-index`, `playwright`, and the
connector SDKs. `torch` and `sentence-transformers` **stay** — Phase 2's
embedding worker needs them.

---

## Stage 3 — Phase 2 target (Day 8, if not cut)

Adds retrieval back as one auditable module. Gated by `KNOWLEDGE_ENABLED`, so
Phase 2 can be cut on Day 8 without a rollback.

```text
  api_server ──> relational_db          system of record, commits FIRST
             ├─> qdrant                 vectors, reconstructible from Postgres
             └─> embedding_worker       in-process, loaded per ingest job,
                                        released after. Not a daemon.
```

| Service | Image | Why |
| --- | --- | --- |
| `qdrant` | `qdrant/qdrant` | dense + **sparse** vectors in one collection — hybrid lexical/semantic without a second service, which is what covers drug codes and dosages |
| `embedding_worker` | inside the backend image | 384-dim English embeddings, on-demand only |

Rules that keep Stage 3 from growing back into Stage 0:

1. **No scheduler.** Nothing is time-triggered; every ingest run has a human
   actor recorded against it.
2. **One writer.** `reference_ingest` is the only code that writes Qdrant.
3. **PostgreSQL first.** Qdrant is a derived store and is rebuildable.
4. **Reconciliation, not sync.** An admin-triggered compare that reports drift;
   it does not auto-repair.
5. Qdrant's default setup has **no authentication**. Its container must be
   private and authenticated in any real deployment.

---

## Service reference

| Service | Stage 0 | Stage 1 | Stage 2 | Stage 3 | Ports | Volume |
| --- | :-: | :-: | :-: | :-: | --- | --- |
| `api_server` | ● | ● | ● | ● | 8080 | storage, model cache |
| `web_server` | ● | ● | ● | ● | — | — |
| `relational_db` | ● | ● | ● | ● | 5432 | `db_volume` |
| `nginx` | ● | ● | ● | ● | 80, 3000 | `../data/nginx` |
| `index` (Vespa) | ● | ● | — | — | 19071, 8081 | `vespa_volume` |
| `background` | ● | — | — | — | — | — |
| `model_server` | ○ | — | — | — | — | model cache |
| `qdrant` | — | — | — | ● | 6333 | qdrant volume |
| `embedding_worker` | — | — | — | ● | in-process | model cache |

● runs  ○ opt-in profile  — not present

### External dependencies (never compose services)

| Dependency | Configured by | Required for |
| --- | --- | --- |
| Luganda→English MT | `TRANSLATION_EN_URL` | Luganda input |
| English→Luganda MT | `TRANSLATION_LUG_URL` | Luganda output |
| OpenAI API | `GEN_AI_API_KEY` | all answers |

---

## Running it

```sh
make up          # start Stage 1
make ps          # what is up
make logs        # tail everything
make api-logs    # tail the API server only
make down        # stop, keep data
make reset       # stop and DESTROY local volumes
```

`make check` runs the same steps CI runs: format, lint, typecheck, unit tests,
and the `deprecated/` import gate.
