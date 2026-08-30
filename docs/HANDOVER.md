# Heal simplification — handover

**Branch:** `simplify/phase-1` · **Date:** 2026-08-28 · **Status:** uncommitted, staged
**Plan:** `docs/architecture-decisions.md` · **Runtime:** `docs/runtime-architecture.md`

Days 1–6 of the two-week plan are done. 177 files changed: 125 renames, 26 new,
26 modified. Nothing is committed — the commit split is at the end of this doc.

---

## Is Vespa gone?

Short answer: **gone from everything that runs, still on disk.**

| Where | State |
| --- | --- |
| `docker-compose.local.yml` (what `make up` runs) | **removed** — 4 services: api, web, postgres, nginx |
| API server boot path (`heal_app/main.py`) | **removed** — `ensure_indices_exist()` deleted from `startup_event` |
| Chat request path | **removed** — `heal/chat/message_flow.py` replaces `stream_chat_message`; no retrieval, no `document_index` import |
| Registered FastAPI routers | **removed** — 11 routers unregistered; none of the survivors reach it |
| `VESPA_*` env in the local compose | **removed** |
| `backend/heal_app/document_index/` on disk | **still there** — 7 files, 72K, imported by nothing live |
| `docker-compose.dev.yml` | **still there** — untouched on purpose; it is the fork's original stack, kept for reference |
| `VESPA_*` in `configs/app_configs.py` | **still there** — dead config, read only by `document_index/` |

So: `make up` starts no Vespa, the app boots without it, and no request touches
it. What remains is unreferenced code and dead config sitting in the repo.

### Why the directory could not be deleted

`document_index/` is one of eight packages held in place by **shared Pydantic
and dataclass types that kept code still imports**. Moving them breaks the live
import graph — I tried it with `heal_app/access/`, the app stopped importing, and
I moved it back.

| Package | Imported by (kept code) | Types involved |
| --- | --- | --- |
| `heal_app/search/` | `chat/models.py`, `chat/load_yamls.py`, `db/chat.py`, `db/models.py`, `db/slack_bot_config.py`, `server/features/persona/models.py`, `server/query_and_chat/models.py` | `SearchType`, `RecencyBiasSetting`, `OptionalSearchSetting`, `IndexFilters`, `BaseFilters`, `QueryFlow` |
| `heal_app/indexing/` | `chat/chat_utils.py`, `llm/utils.py` | `InferenceChunk`, `IndexChunk`, `DocAwareChunk` |
| `heal_app/connectors/` | `db/models.py`, `db/connector.py`, `db/credentials.py` | `Document`, `InputType`, `Section`, `BasicExpertInfo` |
| `heal_app/document_index/` | `db/document.py` | `DocumentIndex`, `UpdateRequest`, `DocumentMetadata` |
| `heal_app/access/` | `indexing/models.py` (itself blocked) | `DocumentAccess` |
| `heal_app/danswerbot/` | `server/manage/models.py` | `SlackBotConfig` |
| `heal_app/one_shot_answer/` | `server/features/persona/api.py` | `qa_block` |
| `heal_app/secondary_llm_flows/` | `server/query_and_chat/chat_backend.py` | `chat_session_naming` (chat rename — a **kept** feature) |

This is dead weight in the image, not live behaviour. Untangling it is the first
item in *Next steps*.

---

## What was built

### `backend/heal/` — 26 modules, all new and Heal-owned

```
heal/config.py              every setting, env-driven, no address in source
heal/logger.py              independent of danswer's indexing-bound logger
heal/safety.py              versioned clinical safety instruction
heal/language/              LanguageService + provider registry (heal_mt)
heal/llm/                   model catalogue, registry, selection
heal/chat/                  message_flow, prompt_builder, stream_processing, export
heal/medical_guidance/      agent, intent, routes, audit
heal/server/api_key.py      service API key, lifted off the ingestion module
```

**The agent is a straight line**, not a loop: classify → fixed route table →
build prompt → stream → audit. The model never picks an action. Emergency
escalation copy is emitted *before* the model is called, so it reaches the user
even if generation produces nothing. `OUT_OF_SCOPE` declines without calling the
model at all. `DOSAGE_OR_MEDICATION` is the only intent that requires a source.

**One LLM call replaces three.** `check_if_need_search`, query rephrasing and
the LLM chunk filter are all folded into the single intent classification.

**Audit events** carry ids, labels, model names and versions — never message
text. Currently structured log lines; `audit.emit()` is the seam for a table
once the Alembic rebaseline lands.

### Translation — the naked IPs are gone

`http://65.108.33.93:4002` and `:5000` appeared at five call sites, two of them
inline copy-paste duplicates of the helper. All now go through
`LanguageService`, with endpoints from `TRANSLATION_EN_URL` /
`TRANSLATION_LUG_URL`, bounded timeouts, bounded retries (connection-level
only — a half-streamed translation is never replayed), typed errors, and
failures that log the URL but never the text.

**No defaults are baked in.** Unset, Luganda chat fails with
`TranslationNotConfigured` naming the variable to set. English is unaffected.

### Model selection

`heal/llm/registry.py` is a catalogue — `gpt-4o-mini` (default), `gpt-4o`,
`gpt-3.5-turbo` (eval baseline, not selectable), `claude-sonnet-4-5`.
`available_models()` filters by the `selectable` flag, the
`HEAL_ENABLED_CHAT_MODELS` allowlist, and whether the provider has an API key.
Adding a model is one line. `admin/keys/openai` is kept.

### UI

White page carried by red and black. Two ramps in `tailwind.config.js` —
`heal.red` (10 stops, `600 #d92d20` primary) and `heal.ink` (11 stops) — with
the existing semantic tokens (`accent`, `link`, `strong`, `background`,
`hover-light`, ~250 usages) remapped onto them. Blue and indigo swept out of the
live surfaces. Retired admin surfaces were deliberately left unstyled.

**Open question:** brand red and error red are now the same hue. `error` is
pitched darker (`#912018`) than `accent` (`#d92d20`), but that is contrast, not
signal — error states need an icon or a wash to carry meaning.

### Infrastructure

- `docker-compose.local.yml` — the Phase 1 stack, 4 services
- `Makefile` — 23 targets; `make check` runs exactly what CI runs
- Images renamed `heal_app/danswer-*` → `khalifan1126/heal-*` across compose, CI
  and the Kubernetes manifests (`heal/` was never our Docker Hub namespace)
- **30 packages removed** from `default.txt`, 8 from `dev.txt`
- Dockerfile: playwright browser install, the `py` CVE cleanup, supervisor
  symlink and `supervisord.conf` copy all removed; `heal/` added (it was
  missing — the image would have failed on import)
- k8s: Vespa and background manifests retired, `VESPA_*` out of the configmap
- CI: unit tests now run (there was **no test step at all** before) and the
  `deprecated/` import gate is enforced

---

## Bugs found and fixed along the way

| Bug | How it surfaced |
| --- | --- |
| `cast` undefined in `administrative.py` — runtime `NameError` on the OpenAI key endpoint | ruff |
| `create_chat_chain` imported from the wrong module in the new chat flow | mypy |
| Intent parser returned `None` for `"Category: EMERGENCY"` — took the first token and gave up | a test I wrote; fixed the parser, not the test |
| `WelcomeModal` fired on `connectors.length === 0`, now always true — every user would land on "Setup your first connector!" | reading the frontend move report |
| `tsconfig.json` did not exclude `src/deprecated`; `next build` would typecheck 51 broken imports in frozen code | frontend agent |
| API key logged in plaintext at startup | reading `startup_event` |
| Chat endpoint logged the full question body | reading the endpoint |
| `heal/` was not copied into the Docker image | reading the Dockerfile |

Two corrections to the plan, from the dependency analysis:
**`tensorflow` is imported in two files, not one** (`search/search_nlp_models.py:6`
as well as `model_server/custom_models.py`), and **`celery` is live in
`alembic/env.py:10,25`** — it cannot be removed until the migration rebaseline
edits that file. Both pins were left in place.

---

## Verification status

**Green:** black (301 files), ruff, mypy on `heal/` under `--disallow-untyped-defs`,
**104 unit tests**, the `deprecated/` import gate, no naked IPs anywhere.

**NOT verified — read this before trusting the build:**

1. **The container has never been built or booted.** Local installs hit
   dependency conflicts twice; stubbing third-party packages broke on
   SQLAlchemy's declarative base. I proved the *internal* import graph resolves
   and reaches no `document_index`, but that is static analysis, not a process.
2. **30 packages were removed from `default.txt`.** A missing runtime-only
   dependency would only show at import or first request.
3. **`npm install` / `next build` never ran** — no `node_modules` locally.
4. **No Luganda round trip was exercised** against real MT services.
5. **The inherited `tests/unit/danswer/` suite could not be collected** locally
   (missing deps). It should collect in CI.

---

## Next steps, in order

### 1. Make it run — half a day

```sh
make up          # first real build; expect missing-dependency failures
make api-logs
```

Work through whatever the build throws. The likely failures are packages from
the Wave 0 removal list that had an indirect consumer. `python -c "import
danswer.main"` inside the container is the fastest check. Then: log in, start a
chat, send an English message, confirm streaming, feedback and CSV export.

Add to CI once green — the dependency analysis recommends this and it is the
gate that would have caught #2 above:

```yaml
- run: python -c "import heal_app.main"
- run: alembic upgrade head   # against a scratch DB
```

### 2. Configure translation, test Luganda — half a day

Set `TRANSLATION_EN_URL` and `TRANSLATION_LUG_URL`. Send a Luganda message and
confirm the round trip: Luganda in → English through the agent → Luganda out,
with the original stored alongside. Until this is set, Luganda chat fails with a
clear config error by design.

### 3. Untangle the shared types — 1–2 days, the real Vespa deletion

This is what actually removes `document_index/` and its seven siblings. Create
`backend/heal/models/` (or `heal_app/shared_models/`) and move the types in the
table above into it, then update the kept importers. Do it one package at a
time, running `make check` between each — `search/` first, since it has the most
importers and unblocks the most.

Verify with the import-graph walk: nothing from `danswer.main` should reach a
retired package. Then `git mv` the eight packages to `deprecated/`, and delete
the `VESPA_*` config from `app_configs.py`.

### 4. Alembic rebaseline — 1 day, needs a production backup first

Plan step [0] has not started. **Back up production and verify the restore
before anything else.** Then squash the 49 migrations into `0001_heal_baseline`,
move the old chain, **stamp production (never upgrade it)**, and make the
`pg_dump --schema-only` diff a CI job.

Sequence this with the `celery` removal — `alembic/env.py:10,25` imports
`ResultModelBase` and both edits touch the same file. One PR, not two racing
ones.

### 5. Wave 1 dependency removals — half a day, after CI is green

`supervisor` (+ Dockerfile lines), `nltk`, `tensorflow` (needs the
`search_nlp_models.py` split — the intent half goes, the embedding half becomes
`heal/knowledge/`), `celery` + `celery-types` (after step 4).

### 6. Then the plan's Week 2

Day 7 fresh-environment rebuild · Day 8 Qdrant go/no-go (**Apache-2.0,
verified** — permissive, no obligation to open-source Heal; use named vectors so
dense + sparse hybrid is designed in before first ingest) · Day 9 clinician eval
set and `MIN_RETRIEVAL_SCORE` **measured, not guessed** · Day 10 load smoke,
README corrected, pilot.

### Also outstanding

- **`admin/feedback` screen** — the plan calls it the highest-value new admin
  screen and it is not built. The clinical review loop needs somewhere to read from.
- **Dead frontend fetches** — the chat page still calls `/manage/connector`,
  `/manage/document-set`, `/query/valid-tags`. They 404 and degrade to empty
  arrays, so they are noise, not breakage. Left alone deliberately: removing
  them shifts `results[]` indices.
- **Orphaned frontend files** — the move left ~20 components and libs with no
  importer. Listed in the agent report; not yet moved.
- **Error-vs-brand red** — see UI section.
- **README** still promises private-source answers. Must be corrected before the
  pilot; the plan flags this.

---

## Suggested commit split

Nothing is committed. Everything is staged on `simplify/phase-1`.

1. `chore: formatting and tooling baseline` — black/ruff across the backend, pyproject, pytest pins, CI test step and deprecated gate
2. `feat(language): LanguageService with env-driven MT endpoints` — `heal/language/` + tests
3. `refactor: route all translation through LanguageService` — the three call sites
4. `feat(llm): model catalogue and selection` — `heal/llm/` + tests
5. `feat(agent): MedicalGuidanceAgent, intent routing, safety, audit` — `heal/medical_guidance/`, `heal/safety.py`, `heal/chat/` + tests
6. `refactor(chat): Phase 1 chat flow replaces stream_chat_message` — endpoint switch, `startup_event` stripped, routers unregistered
7. `chore: move retired backend modules to deprecated/` — pure `git mv`
8. `chore: move retired frontend routes to deprecated/` — pure `git mv`, 90 files
9. `feat(ui): red and ink palette on a white page`
10. `chore: deployment — local stack, image rename, dependency removals, Makefile, docs`

Commits 7 and 8 must contain **only** renames, so review stays trivial.
