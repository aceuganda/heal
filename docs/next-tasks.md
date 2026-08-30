# Next tasks

**Written:** 2026-08-29
**Companion to:** `docs/runtime-architecture.md` (what runs), `docs/deprecated/MOVED.md` (what was retired)

What is left to make Heal a good chat assistant for a health worker. Ordered by
what unblocks the most, not by calendar. There is no day schedule here on
purpose — the previous one became a way of deferring work rather than doing it.

Everything below is either something found broken this cycle, or a known gap in
what shipped. Nothing here is speculative.

---

## 1. Retrieval gaps — the RAG shipped incomplete

Retrieval works end to end: chunk, embed (dense + sparse), pre-filter, score
floor, diversity cap, cite. Two deliberate shortcuts need closing before it is
trustworthy with real clinical documents.

### 1.1 Ingest only accepts plain text — DONE 2026-08-29

`heal/knowledge/extract.py` handles text, Markdown, PDF (`pypdf`) and DOCX
(`python-docx`, reading tables as well as paragraphs, because that is where
dosages live).

A **scanned PDF is refused, not indexed**: pages with no text layer would
otherwise produce an approved, citable source containing nothing. The error
says to run OCR first.

Still outstanding here: no OCR path, and table-heavy guidelines still flatten
into prose. Check extraction output on a real guideline before approving it.

### 1.2 PostgreSQL is not yet the system of record

The plan is explicit: Postgres commits first, Qdrant is derived and
reconstructible. What shipped writes **only Qdrant**. Source metadata,
versions and chunk text live in the Qdrant payload.

Consequences today: losing the Qdrant volume loses the corpus; there is no SQL
view of what is approved; and the reconcile step described in the plan has
nothing to compare against.

Needs `source`, `source_version` and `chunk` tables, written before the Qdrant
upsert, with the point id stored alongside. This is a forward migration — see
task 3, which it should be sequenced after.

### 1.3 `MIN_RETRIEVAL_SCORE` is a placeholder

Default `0.35`, chosen by nobody. This is the number that decides when Heal
refuses to give a dose. It is a clinical-safety parameter, not a tuning knob.

Set it from measured results: build a query set from real health-worker
questions, run `make kb-search`, and read the printed scores for hits that
should and should not have been returned. Record the chosen value **and the
evidence** in this repo. Deliberately include drug-code and abbreviation cases
(`TDF/3TC/DTG`, `500mg BD`, ICD codes) — that is what the sparse half exists
for and it should be proven, not assumed.

### 1.4 No admin UI for sources — DONE 2026-08-29

`admin/sources` is built: upload with metadata, approve/withdraw, delete, and a
**test-retrieval panel that shows raw scores including hits below the floor**.
That panel is the tool for task 1.3 — the floor cannot be chosen sensibly
without seeing what a query nearly matched.

Backed by `heal/server/knowledge_api.py` under `/manage/knowledge`, using the
same `current_admin_user` dependency as the rest of the admin surface (a no-op
when `AUTH_TYPE=disabled`, so a local stack is open without a special bypass).

Not yet built: an ingest-jobs view (`admin/jobs`). Run records exist as
`IngestResult` but are only logged, not stored — they need task 1.2's tables.

---

## 2. The image is 2.81 GB carrying a stack it never runs

`requirements/default.txt` still pins `tensorflow`, `torch`, `nltk`, `celery`
and `supervisor`. That is roughly 350 MB of wheels for code no request reaches.
For scale: Qdrant, the whole vector database, is 200 MB.

Remove in this order, because each is blocked by the one before it:

| Package | Blocked by | Notes |
| --- | --- | --- |
| `supervisor` | **nothing** | Zero importers anywhere in live code. Removable today. |
| `nltk` | `heal_app/search/search_runner.py` | Goes with the `search/` untangle (task 4). |
| `tensorflow` | `heal_app/search/search_nlp_models.py` | Same. This is the 263 MB one. |
| `celery` | `alembic/env.py` | Goes with the rebaseline (task 3). |

`torch` and `sentence-transformers` **stay** — the embedding worker needs them.

---

## 3. Alembic rebaseline — not started

Step [0] of the procedure in `docs/architecture-decisions.md` has not been done:
**there is no verified production backup**. Nothing else in that procedure may
begin until there is one.

The rest is unchanged and still correct: squash the 49 inherited migrations into
`0001_heal_baseline`, move the old chain to `deprecated/alembic_danswer/`,
**stamp production — never upgrade it**, and make the schema diff a CI job.

Sequence the `celery` removal into the same pull request: both edit
`alembic/env.py`, and two racing changes to that file is how a migration chain
gets corrupted.

Task 1.2's new tables land **after** this, not before.

---

## 4. Untangle the shared types — the real Vespa deletion

Eight packages are on the deprecation map but cannot move: live code imports
shared Pydantic and dataclass types from inside them (`SearchType`,
`InferenceChunk`, `Document`, `DocumentAccess`, …). The full table is in
`docs/deprecated/MOVED.md` under *Still entangled*.

Create a neutral module, move the shared types into it, update the importers one
package at a time with `make check` between each. Start with `heal_app/search/` —
most importers, unblocks the most. Then `git mv` the eight packages to
`deprecated/` and delete `VESPA_*` from `app_configs.py`.

This is what finally deletes Vespa from the repository, and it unblocks the
`tensorflow` and `nltk` removals in task 2.

### 4.1 Twelve latent broken imports

A static walk of the live tree found `danswer.server.documents.models` imported
from 12 sites in code that no longer exists on the live tree — `access/`,
`connectors/`, `db/connector.py`, `db/credentials.py`, `db/document.py`,
`db/index_attempt.py`.

None are reachable from `danswer.main`, so nothing crashes today. They will
surface the moment one of those modules is imported. Clean them up as part of
the untangle rather than one traceback at a time.

### 4.2 The `deprecated/` gate has a blind spot

`make deprecated-gate` greps for imports **of** `deprecated`. It cannot see a
live module importing a path that now exists **nowhere** — which is exactly the
bug that stopped `danswer.main` importing at all.

The `import heal_app.main` step now in CI catches it. Consider also adding the
static import walk as a test: it found all 13 sites in under a second.

---

## 5. Secrets are in a ConfigMap

`GEN_AI_API_KEY`, `QDRANT_API_KEY` and `SMTP_PASS` sit in
`deployment/kubernetes/env-configmap.yaml`. A ConfigMap is readable by anyone
with namespace read access and its values turn up in logs and `kubectl describe`
output.

A `danswer-secrets` Secret already exists and is wired correctly — but only to
Postgres. Move the three keys into it and reference them with `secretKeyRef`.
Rename the Secret to `heal-secrets` while doing it.

---

## 6. Kubernetes has no Helm chart and no Qdrant

- **No chart.** `deployment/kubernetes/` is 8 raw manifests applied with
  `kubectl apply -f`. There is no `Chart.yaml` anywhere in the repo. A chart
  would make the image tag, the secret/config split and the replica count
  values rather than edits — which is most of task 5 and the image-naming
  problem solved structurally.
- **No Qdrant manifest.** Compose has the `knowledge` profile; Kubernetes has
  only the env keys. Retrieval cannot run on the cluster at all today.

---

## 7. Chat quality — the actual product

Everything above is plumbing. These change what a health worker experiences.

- **`admin/feedback` screen.** The plan calls it the highest-value new admin
  screen and it is still not built. Answer feedback is collected and has nowhere
  to be read. The clinical review loop depends on it.
- **No Luganda round trip has ever been run.** `TRANSLATION_EN_URL` and
  `TRANSLATION_LUG_URL` are unset, so Luganda chat fails by design. Until it is
  tested against the real MT services, half the product is unverified.
- **Translation quality is on the clinical critical path.** It needs its own
  English↔Luganda medical-phrase test set — drug names, dosage units, negation,
  uncertainty — run before rollout and in CI after.
- **Citation display convention.** A Luganda answer currently renders with
  English source titles. Decide the convention; do not machine-translate source
  titles.
- **Model choice is untested.** `gpt-4o-mini` is a default nobody measured.
  Test it on the eval set, against at least one stronger model, before the pilot.
- **Dead frontend fetches.** The chat page still calls `/manage/connector`,
  `/manage/document-set` and `/query/valid-tags`. They 404 and degrade to empty
  arrays — noise, not breakage, but it makes real errors harder to spot.
- **Error red vs brand red.** Same hue. Error states need an icon or a wash,
  not just a darker shade.
- **`README.md` still promises private-source answers.** It was wrong when
  retrieval was off. It is now *arguably* right — but only once a source is
  actually approved. Rewrite it to say what is true.

---

## 8. The Danswer → Heal package rename — DONE 2026-08-29

`backend/danswer/` is now `backend/heal_app/`: 197 modules moved, imports
rewritten in 139 files, entrypoint `uvicorn heal_app.main:app`, and
`DANSWER_VERSION` replaced by `HEAL_VERSION` in `heal_app/__init__.py` and
`web/next.config.js`.

Three things the rename surfaced, worth remembering if a similar sweep is ever
done again:

- **A blanket `danswer.` → `heal_app.` replace would have corrupted URLs.**
  `docs.danswer.dev`, `danswer.ai` and `danswer.atlassian.net` all appear in
  comments. Only import statements and fully-quoted module paths were rewritten.
- **Two config values were filesystem paths, not module paths.** `PROMPTS_YAML`
  and `PERSONAS_YAML` pointed at `./danswer/chat/*.yaml`, and
  `load_chat_yamls()` runs at startup — missing them would have crashed the API
  on boot with `FileNotFoundError`, after everything else looked fine.
- **Six dynamic module lookups were plain strings**, in
  `fetch_versioned_implementation` calls and test `mocker.patch` targets. An
  import-only rewrite leaves those to fail at runtime, not at import.

`backend/deprecated/` still imports `danswer.*`. That is deliberate: it is
frozen text, excluded from lint, type-check and test collection, and imported
by nothing.
