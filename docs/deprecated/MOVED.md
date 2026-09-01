# Moved to `deprecated/`

Every retirement gets one line here. Nothing under `deprecated/` is imported,
registered, linted, type-checked or tested — it is frozen text kept so that a
removal can be reviewed and reverted cheaply. Deletion is a separate change
after the pilot runs clean.

See `docs/architecture-decisions.md` § *The decisions that shape everything
else* (D5) for the rules.

> **Package rename, 2026-08-29.** The live application package moved from
> `backend/danswer/` to `backend/heal_app/`. Paths written `backend/danswer/...`
> below describe the tree as it was when each entry was written and are left
> unchanged so the record stays accurate; read them as `backend/heal_app/...`
> for anything still on the live tree.

| Date | From | To | Reason | Replaced by |
| --- | --- | --- | --- | --- |
| 2026-08-28 | `backend/danswer/utils/translation.py` | `backend/deprecated/danswer/utils/translation.py` | Called two hard-coded public IPs over plain HTTP with no timeout, auth, retry or failure path. | `backend/heal/language/` (`LanguageService` + `heal_mt` provider) |
| 2026-08-28 | `web/src/app/search/` | `web/src/deprecated/app/search/` | Search page retired; the first release is chat-first and makes no private-document claim. | `web/src/app/chat/` |
| 2026-08-28 | `web/src/components/search/` (13 of 18 files) | `web/src/deprecated/components/search/` | Search-page UI: result list, quotes, QA feedback, search bar, search-type selector. Five files held back — see the note below this table. | — |
| 2026-08-28 | `web/src/lib/search/` (6 of 9 files) | `web/src/deprecated/lib/search/` | Search-page client: streaming QA, question validation, keyword mode, cancellable fetch, search-session helpers. Three files held back — see the note below this table. | `heal/medical_guidance/` on the backend |
| 2026-08-28 | `web/src/app/chat/documentSidebar/` | `web/src/deprecated/app/chat/documentSidebar/` | Document-selection UI; there is no document set to select from in phase 1. | — |
| 2026-08-28 | `web/src/app/admin/connectors/` | `web/src/deprecated/app/admin/connectors/` | Admin pages for ~20 external connectors, none of which serve the MVP. | — |
| 2026-08-28 | `web/src/app/admin/connector/` | `web/src/deprecated/app/admin/connector/` | Per-connector-credential-pair admin page. | — |
| 2026-08-28 | `web/src/app/admin/add-connector/` | `web/src/deprecated/app/admin/add-connector/` | Connector picker page. | — |
| 2026-08-28 | `web/src/app/admin/indexing/` | `web/src/deprecated/app/admin/indexing/` | Indexing-status page; there is no background indexing in phase 1. | `admin/jobs` in phase 2 |
| 2026-08-28 | `web/src/app/admin/documents/explorer/` | `web/src/deprecated/app/admin/documents/explorer/` | Vespa-backed document browser. | `admin/sources` in phase 2 |
| 2026-08-28 | `web/src/app/admin/documents/sets/` | `web/src/deprecated/app/admin/documents/sets/` | Document sets; one approved library replaces them. | `admin/sources` in phase 2 |
| 2026-08-28 | `web/src/app/admin/documents/feedback/` | `web/src/deprecated/app/admin/documents/feedback/` | Wrote `chunk.boost`, a live 0.5x-2.0x ranking multiplier over clinical sources. Removing it is a deliberate removal of a ranking input, not an accident. | Score floor + admin-set clinician boost (phase 2.5) |
| 2026-08-28 | `web/src/app/admin/bot/` | `web/src/deprecated/app/admin/bot/` | Slack bot admin; the Slack bot is retired. | — |
| 2026-08-28 | `web/src/app/admin/personas/` (6 of 8 files) | `web/src/deprecated/app/admin/personas/` | Persona editor and table; D3 fixes one agent, so there is nothing to edit. Two files held back — see the note below this table. | `MedicalGuidanceAgent` |
| 2026-08-29 | `deployment/docker_compose/docker-compose.prod.yml` | `deployment/deprecated/docker-compose.prod.yml` | Danswer-era production stack: `index` (Vespa 8.277.17), `background` (supervisord fleet) and `model_server`, plus `VESPA_HOST=index` on two services. | A new four-service `docker_compose/docker-compose.prod.yml` |
| 2026-08-29 | `deployment/docker_compose/docker-compose.prod-no-letsencrypt.yml` | `deployment/deprecated/docker-compose.prod-no-letsencrypt.yml` | Same stack again, differing only in TLS. The new prod file covers both shapes through `NGINX_CONF_TEMPLATE`, so there is one tested compose file rather than two that drift. | `docker-compose.prod.yml` without `--profile letsencrypt` |

## Deployment changes of 2026-08-29

Not moves, but they retire the same machinery and belong in the same log.

| What | Change | Reason |
| --- | --- | --- |
| `backend/Dockerfile` | `zip` dropped from the apt install; `DANSWER_VERSION` build arg renamed `HEAL_VERSION` | `zip` existed only to package the Vespa app bundle. `DANSWER_VERSION` is still exported as an env var because `danswer/__init__.py` reads it — the package rename is a post-pilot change. |
| `web/Dockerfile` | Same build-arg rename | `next.config.js` reads `DANSWER_VERSION`, so the image still exports it. |
| `backend/.dockerignore` | Excludes `deprecated/`, `tests/`, and `danswer/document_index/vespa/app_config/` | The Vespa schema and `services.xml` are data files, read only by `VespaIndex.ensure_indices_exist()`, which nothing calls. The Python package still ships because `db/document.py` imports `DocumentMetadata` from `document_index/interfaces.py` — see *Still entangled* below. |
| `web/.dockerignore` | Excludes `src/deprecated` | Keeps retired routes out of the build context entirely, not just out of the typecheck. |
| `deployment/kubernetes/env-configmap.yaml` | Dropped the indexing, Dask, reranking, model-server and DanswerBot keys; added the translation, model-selection and knowledge keys | Every dropped key fed a service that no longer runs. |
| `deployment/kubernetes/api_server-service-deployment.yaml` | `file-connector-pvc` unmounted; `/health` readiness and liveness probes added | The connector volume went with the connectors. The PVC itself is left declared — deleting a PVC destroys data. |
| Compose files | `qdrant` added behind a `knowledge` profile, `KNOWLEDGE_ENABLED=false` | Phase 2 becomes a flag flip rather than a stack rewrite. Nothing starts it by default. |
| All images | `heal/heal-*` -> `khalifan1126/heal-*` across compose, CI and Kubernetes | `heal/` is not an account we control on Docker Hub. A push there fails, and a pull there fetches a stranger's image. `deployment/deprecated/` is left as-is: frozen text, nothing deploys from it. |
| `deployment/kubernetes/*-deployment.yaml` | `imagePullPolicy: Never` -> `IfNotPresent` | `Never` requires the image to already exist on the node, so images CI published to Docker Hub could never reach the cluster. The two halves of the pipeline were disconnected. |
| `deployment/kubernetes/web_server-service-deployment.yaml` | image repo `heal-frontend` -> `heal-web` | It was the only place using `heal-frontend`; compose and CI both said `heal-web`. A deploy would silently look for an image nothing ever builds. |


## Held back from the 2026-08-28 frontend move

Three of the frontend paths in the deprecation map are imported by code Heal
keeps. Per the deprecation policy these files were **not** moved; re-homing them
is a behaviour change and belongs in its own commit.

| Held back | Imported by (live) | What it is |
| --- | --- | --- |
| `web/src/lib/search/interfaces.ts` | `app/chat/Chat.tsx`, `app/chat/interfaces.ts`, `app/chat/lib.tsx`, `app/chat/message/Messages.tsx`, `app/chat/modifiers/ChatFilters.tsx`, `app/chat/modifiers/SelectedDocuments.tsx`, `lib/documentUtils.ts`, `lib/hooks.ts`, `lib/sources.ts` | `DanswerDocument`, `Filters`, `SourceMetadata` and friends — the shared document/filter types |
| `web/src/lib/search/utils.ts` | `app/chat/Chat.tsx` | filter/tag helpers |
| `web/src/lib/search/streamingUtils.ts` | `app/chat/lib.tsx` | SSE stream helpers used by the chat send path |
| `web/src/components/search/SearchLanguageSelector.tsx` | `app/chat/Chat.tsx` | English/Luganda selector — Heal-added, belongs to chat |
| `web/src/components/search/filtering/Filters.tsx` | `app/chat/modifiers/ChatFilters.tsx` | chat filter panel |
| `web/src/components/search/DateRangeSelector.tsx`, `filtering/FilterDropdown.tsx`, `filtering/TagFilter.tsx` | `components/search/filtering/Filters.tsx` (above) | transitive dependencies of the kept filter panel |
| `web/src/app/admin/personas/interfaces.ts` | `app/chat/ChatPage.tsx`, `ChatIntro.tsx`, `ChatPersonaSelector.tsx`, `Chat.tsx`, `page.tsx`, `lib/types.ts` | `Persona` / `Prompt` types the chat UI still reads |
| `web/src/app/admin/personas/lib.ts` | `app/chat/page.tsx` (`personaComparator`) | persona API client + comparator |

The `/admin/personas` route itself is gone (`page.tsx` moved); only these two
non-route modules remain in that directory.
| 2026-08-28 | `backend/danswer/chat/process_message.py` | `backend/deprecated/danswer/chat/process_message.py` | 543-line function with ten inline branches; every branch assumed Vespa. | `backend/heal/chat/message_flow.py` |
| 2026-08-28 | `backend/danswer/server/query_and_chat/query_backend.py` | `backend/deprecated/danswer/server/query_and_chat/query_backend.py` | Search-page backend; router no longer registered. | — (search page retired) |
| 2026-08-28 | `backend/danswer/server/documents/` | `backend/deprecated/danswer/server/documents/` | Connector, credential and cc-pair admin backends. | — (no connectors in the MVP) |
| 2026-08-28 | `backend/danswer/server/gpts/` | `backend/deprecated/danswer/server/gpts/` | GPTs integration; reached Vespa. | — |
| 2026-08-28 | `backend/danswer/server/danswer_api/` | `backend/deprecated/danswer/server/danswer_api/` | Connector ingestion API. | `backend/heal/server/api_key.py` for the key helper |
| 2026-08-28 | `backend/danswer/server/features/document_set/` | `backend/deprecated/danswer/server/features/document_set/` | One approved library, no document sets. | — |
| 2026-08-28 | `backend/danswer/server/manage/slack_bot.py` | `backend/deprecated/danswer/server/manage/slack_bot.py` | Slack bot admin backend. | — |
| 2026-08-28 | `backend/danswer/utils/acl.py` | `backend/deprecated/danswer/utils/acl.py` | Source-level ACL sync to Vespa. | — |
| 2026-08-28 | `backend/danswer/background/` | `backend/deprecated/danswer/background/` | Celery + Beat + Dask + Slack listener fleet. Phase 1 runs no background process. | — (Phase 2 adds one on-demand ingest job) |
| 2026-08-28 | `backend/model_server/` | `backend/deprecated/model_server/` | Embedding + TensorFlow intent model server. | Phase 2 `embedding_worker` |
| 2026-08-28 | `backend/Dockerfile.model_server` | `backend/deprecated/Dockerfile.model_server` | No worker fleet in Phase 1. | — |
| 2026-08-28 | `backend/supervisord.conf` | `backend/deprecated/supervisord.conf` | Supervisor ran only the background fleet. | — |
| 2026-08-28 | `deployment/kubernetes/vespa-service-deployment.yaml` | `deployment/deprecated/vespa-service-deployment.yaml` | Vespa retired. | Phase 2 Qdrant |
| 2026-08-28 | `deployment/kubernetes/background-deployment.yaml` | `deployment/deprecated/background-deployment.yaml` | The supervisord fleet. | — |
| 2026-08-28 | `.github/workflows/docker-build-push-model-server-container-on-tag.yml` | `deployment/deprecated/docker-build-push-model-server-container-on-tag.yml` | Built Dockerfile.model_server, now retired. | — |

## Extracted, not renamed (2026-08-28)

These were part of files Heal keeps, so the move could not be a pure `git mv`.
The retired code was cut out and placed under `deprecated/` for reference; the
surviving half stayed where it was.

| From | To | Reason | Replaced by |
| --- | --- | --- | --- |
| `create_search_feedback` from backend/danswer/server/query_and_chat/chat_backend.py | `backend/deprecated/danswer/server/query_and_chat/document_search_feedback.py` | Wrote `chunk.boost`, a live 0.5x-2.0x ranking multiplier over clinical sources. | Phase 2.5 admin-set clinician boost |
| doc-boosts / doc-hidden / deletion-attempt from backend/danswer/server/manage/administrative.py | `backend/deprecated/danswer/server/manage_administrative.py` | Same crowd-boost ranking control, plus connector deletion. The OpenAI key admin stays. | Phase 2.5 clinician boost |
| `update_document_boost`, `update_document_hidden`, `create_doc_retrieval_feedback` from backend/danswer/db/feedback.py | `backend/deprecated/danswer/db_feedback_document_index.py` | Wrote boost/hidden straight through to Vespa. `create_chat_message_feedback` is PostgreSQL-only and stays. | — |

## Still entangled — not yet movable (2026-08-28)

These packages are on the deprecation map but cannot move yet: kept code imports
shared Pydantic/dataclass types from inside them. Moving them would break the
live import graph. Untangling means relocating the shared types to a neutral
module, which is its own change.

| Package | Blocked by | Shared types involved |
| --- | --- | --- |
| `danswer/search/` | `chat/models.py`, `chat/load_yamls.py`, `db/chat.py`, `db/models.py`, `db/slack_bot_config.py`, `server/features/persona/models.py`, `server/query_and_chat/models.py` | `SearchType`, `RecencyBiasSetting`, `OptionalSearchSetting`, `IndexFilters`, `BaseFilters`, `QueryFlow` |
| `danswer/indexing/` | `chat/chat_utils.py`, `llm/utils.py` | `InferenceChunk`, `IndexChunk`, `DocAwareChunk` |
| `danswer/connectors/` | `db/models.py`, `db/connector.py`, `db/credentials.py` | `Document`, `InputType`, `Section`, `BasicExpertInfo` |
| `danswer/document_index/` | `db/document.py` | `DocumentIndex`, `UpdateRequest`, `DocumentMetadata` |
| `danswer/access/` | `indexing/models.py` (itself blocked) | `DocumentAccess` |
| `danswer/danswerbot/` | `server/manage/models.py` | `SlackBotConfig` |
| `danswer/one_shot_answer/` | `server/features/persona/api.py` | `qa_block` |
| `danswer/secondary_llm_flows/` | `server/query_and_chat/chat_backend.py` | `chat_session_naming` (chat rename, a kept feature) |

None of these are on the runtime path any more -- nothing reaches Vespa, and the
app boots without it. They are dead weight in the image, not live behaviour.
