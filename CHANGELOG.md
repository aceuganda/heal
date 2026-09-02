# Changelog

Notable changes to Heal, newest first.

**How to use this file.** One entry per change that a person outside the commit
would want to know about: behaviour a health worker or an administrator can
see, a schema change, a new configuration value, or a decision that constrains
future work. Not every commit — a refactor nobody can observe does not need a
line here.

Entries say *what changed and why it matters*, not which files moved. When a
change carries a risk or a migration step, say so in the entry rather than
leaving it to be discovered.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are not tagged yet, so changes accumulate under **Unreleased** until
the first pilot release.

---

## [Unreleased]

### Changed

- **The lexical half of retrieval now weights rare terms by how rare they are.**
  Until now the sparse vector was raw term frequency: a term counted only by how
  often it appeared in its own chunk, with no corpus statistics. `TDF/3TC/DTG` —
  the most discriminating token in an ART question — was weighted no more
  heavily than `patient`, which appears in nearly every chunk. The lexical stage
  exists specifically to catch drug codes and abbreviations, and it was
  systematically under-weighting them. Qdrant computes inverse document
  frequency inside the engine, so the fix is a collection setting plus the raw
  term frequencies we already write. Controlled by `HEAL_SPARSE_IDF`, default
  on. **This was not a limitation of the architecture.** The running Qdrant has
  supported engine-side IDF since 1.10 and the deployment is on 1.19; the client
  was pinned at 1.9.0, which predates it. The architecture document had recorded
  corpus statistics as something given up when Vespa was removed. That was
  wrong, and the correction is written up as *The IDF gap*.

  **This change requires a re-ingest, and it moves the score floor.** Two things
  an operator has to know:

  1. The IDF modifier can only be set when a collection is created. An existing
     collection keeps scoring without corpus statistics no matter what the
     configuration says. `ensure_collection` now detects that mismatch and logs
     it, `/knowledge/status` reports `sparse_idf_configured` and
     `sparse_idf_active` separately, and `sparse_idf_needs_reingest` says which
     state the deployment is in. Recreating the collection and re-ingesting the
     corpus is what actually applies it. Qdrant holds derived data only — it is
     rebuildable from the approved sources, and no relational table is touched.
  2. IDF changes the scale of the sparse score, so `HYBRID_ALPHA` (0.6) and
     `MIN_RETRIEVAL_SCORE` (0.35) no longer mean quite what they meant when they
     were chosen. The fusion normalises the sparse half per result set to keep
     the weight meaningful, but the floor is a clinical-safety parameter that
     decides when Heal refuses to give a dose, and it must be re-derived on the
     clinician evaluation set. `/knowledge/status` now carries
     `min_retrieval_score_unvalidated` so this is visible rather than assumed.

- **`qdrant-client` 1.9.0 → 1.19.0**, matching the server already deployed. The
  1.19 client removed `search()`, so both halves of the hybrid query moved to
  `query_points()`. That is also the endpoint that performs fusion server-side,
  which is what makes Reciprocal Rank Fusion available later without rewriting
  the query path a second time. **Requires reinstalling backend dependencies**;
  the code will not run against 1.9.0.

### Added

- **A retrieval playground for administrators.** `MIN_RETRIEVAL_SCORE` decides
  when Heal refuses to give a dose, and its current value is openly a
  placeholder that has to be measured rather than reasoned about. The new
  `/admin/playground` screen runs one question through the whole pipeline and
  shows what happened: the rewritten query beside the original, every candidate
  the store returned *before* the score floor and the diversity cap discarded
  any of them — with the floor drawn through the list so a near-miss is visible
  and its shortfall stated — the route the label selected, the answer with its
  `[n]` markers resolved, and the time each stage took. The score floor, hybrid
  weight, top-k values, per-source cap, and both the chat and classifier models
  can be changed for the run. **The settings are per-request and die with the
  request**: they never touch the running configuration, so an administrator
  experimenting with a floor cannot change what a health worker is told at that
  moment. The screen says so, and reports the settings the server says it used
  rather than whatever the controls currently show. Behind the same gate as
  user management.
- **Admin playground.** A screen for trying different retrieval settings and
  models against a real question and seeing every candidate, its dense, sparse
  and fused scores, and whether it passed the score floor or was cut by the
  per-source cap. Settings apply to that one run only and never change what
  health workers receive.
- **The question is understood before it is searched.** One structured call now
  produces both the safety label and a cleaned, specific version of the question
  for retrieval — spelling and grammar repaired, references from earlier turns
  resolved, phrased the way a guideline would phrase it. The dense half of the
  search embeds the rewrite; the lexical half also sees the user's own words, so
  a drug code they typed still matches exactly even when the rewrite generalised
  it. A failed or unusable rewrite falls back to the original text with a safe
  label, which is how the system behaved before this existed.
- **A loading state that says what is happening.** The wait between sending a
  question and the first token is the longest silence in the product. It now
  shows the African continent as a dot map with a pulse travelling across it,
  beside a line of text naming the current step. Both honour
  `prefers-reduced-motion`.
- **Citations are real.** `[n]` markers in an answer are extracted from the
  finished text, mapped to the passage each one points at, and stored with the
  message. In the chat they render as links that open the cited passage; a
  marker the model invented (`[9]` when five passages were supplied) stays plain
  text rather than becoming a link to nothing.
- **Plain-language glosses.** `GET /chat/reference/{id}/gloss` explains one
  cited passage in at most two sentences, generated on demand and cached on the
  row. The gloss never replaces the passage, the model sees only the passage —
  not the question or the history — and a failure shows no gloss rather than a
  guess.
- **Three-tier roles** — `SUPER_ADMIN`, `ADMIN`, `MEMBER` — checked by rank
  rather than equality. The last super admin cannot be demoted. Migration
  `a1c4f7d2e9b0` converts existing rows and widens the column to `varchar(11)`.
- **User management** for administrators: create an account with a chosen role,
  change a role, and a paginated, filterable user list with an explicit
  `ORDER BY email` (without one, Postgres can return a row on two pages and
  never return another).
- **Bootstrap administrator.** One account seeded at startup, only into a
  completely empty user table, from `HEAL_BOOTSTRAP_ADMIN_EMAIL` /
  `HEAL_BOOTSTRAP_ADMIN_PASSWORD`. It cannot overwrite an account or reset a
  password. A known-weak password warns loudly and proceeds.
- **Indexing reports progress.** Uploads return a job id immediately and the
  admin UI polls it. Chunks are embedded and written in batches, so a long
  guideline shows movement instead of a blank screen for several minutes.
- **Hybrid retrieval.** A sparse lexical vector alongside the dense one, so
  drug codes and dosages (`TDF/3TC/DTG`, `500mg BD`) match exactly rather than
  only semantically. Restores the capability that was lost with Vespa's BM25,
  without a second service.
- **Frontend unit tests.** `vitest` and `make test-web`; the project had no
  frontend test runner before.

### Changed

- **Indexing no longer takes the API down.** Extraction and embedding moved off
  the event loop into a thread pool. One upload previously froze the whole API —
  `/health` itself timed out. Verified with 25/25 health checks passing during
  an upload.
- **nginx read timeout raised to 600s.** The 60s default cut off any real
  indexing request.
- **The stack starts with one command.** Qdrant left the optional compose
  profile and `KNOWLEDGE_ENABLED` defaults to `true`; the `kb-*` make targets
  are gone and that work happens in the admin UI. A stack you have to remember
  to start twice is a stack that boots half broken.
- **Translation is configured, not hard-coded.** The private MT services are
  reached through a provider interface with URLs from the environment, connect
  and read timeouts, bounded retries on connection failures only, and an
  optional bearer token. Previously: plain HTTP to hard-coded public IP
  addresses with no timeout, where a hung service hung the entire chat request.

### Fixed

- **Sparse-vector index collision.** `sparse_vector()` emitted one entry per
  token in a 2^20 hash space; two tokens hashing to the same slot produced a
  duplicate index and Qdrant rejected the whole write with
  `422 ... indices: must be unique`. Weights now accumulate per index. The bug
  predated batching and never appeared because a one-chunk test document has too
  few tokens to collide.
- **Super admins were locked out of admin screens.** `current_admin_user` tested
  `role != ADMIN`, which denied every super admin. The same equality bug existed
  in `Layout.tsx`, `Header.tsx` and `ChatSidebar.tsx`. All now use a rank check.
- **Feedback is a four-star rating, not a thumbs pair.** 1 is worst, 4 best.
  Four rather than five because there is no neutral middle to hide in: a health
  worker has to come down on one side of "was this usable", and a five-point
  midpoint is where undecided answers go to be uncounted. The control is inline
  under the answer, one click, submitted immediately — the modal is gone.

  **The comment is opt-in.** Rating and commenting are separate actions, so
  confirming an answer was fine costs one click and never opens a form.

  Ratings feed the sigmoid aggregate described in
  `docs/architecture-decisions.md` § Feedback: a bounded, confidence-weighted
  score that starts neutral and moves further as ratings accumulate, so one
  irritated afternoon cannot condemn a guideline and a much-used source cannot
  accumulate an unbounded score. Surfaced to admins at `/manage/feedback/answers`
  and `/manage/feedback/sources`, worst first. **It does not affect retrieval
  ranking** — it exists to send a human to look at a guideline.

  `chat_feedback` gains a nullable `rating` column with a range check
  (migration `b7e3c9a41d52`). `is_positive` is kept, not dropped: older rows
  carry a real judgement, and backfilling a thumbs-up into a number would be a
  guess. Those rows are counted as thumbs and skipped by the aggregate.

- **The feedback comment read as required when it never was.** A rating always
  submitted with or without one, but the dialog said "Provide additional
  feedback" and offered only "Submit feedback", so a health worker who just
  wanted to press 👎 was left facing a form. It now says the rating is already
  recorded, marks the box optional, and offers Skip. A blank comment is sent as
  null rather than an empty string, so "rated, no comment" and "opened the box
  and typed nothing" stay distinguishable.
- **Duplicate React keys on reference chips.** They were keyed by
  `document_id`, which is `source_id:version` and therefore shared by every
  passage from one guideline. Two citations from the same source collided.
- **Reference glosses were generated twice.** The drawer's content component is
  mounted twice — once for the desktop panel, once for the mobile sheet, with
  only CSS deciding which is visible — so fetching inside it ran two model calls
  per opened citation.
- **The reference panel could not be closed on desktop.** `ChatLayout`'s header
  is `absolute top-0` and overlays the panel, so the close button sat underneath
  it. The panel now clears the header the way the chat sidebar already did.
- **The chat sidebar could only be collapsed from the header.** Its click-outside
  overlay is mobile-only; it now carries its own close button at any width.
- **The language switch floated away from the input on wide screens.** Its
  wrapper's `self-start` overrode the row's `items-end` at every breakpoint
  rather than only in the stacked mobile layout.
- **Three 404s on every chat page load.** The chat page still fetched
  `/manage/connector`, `/manage/document-set` and `/query/valid-tags`, whose
  routers went with the connector fleet. The values were already empty; only the
  failed requests and their log lines are gone.
- **`build-web`, `build-api`, `restart-web` and `restart-api` never worked.** The
  retry macro put the service name before the subcommand — `docker compose
  web_server build` — which docker rejects. `build` and `up` were unaffected
  because they pass no service name.

### Changed

- Reference excerpts render one size smaller, so a long passage fits without
  being truncated.

### Added

- **A self-hosted model can serve chat, with the cloud model as a fallback.**
  Set `HEAL_SELF_HOSTED_URL` (an OpenAI-compatible vLLM endpoint, including
  `/v1`), `HEAL_SELF_HOSTED_MODEL`, `HEAL_SELF_HOSTED_CONTEXT_TOKENS` and
  `HEAL_SELF_HOSTED_API_KEY` and it joins the catalogue as the model id
  `self-hosted`. See `deployment/docker_compose/env.self-hosted.template`.

  **The URL is operator configuration and nothing else.** It is never read from
  a request and cannot be set through the UI: a server that fetches an address
  a caller chose is a server that will read the cloud metadata endpoint on their
  behalf. It is also never sent to the browser.

  When the endpoint does not answer, the message is retried once and then served
  by the configured cloud model, which needs a real `GEN_AI_API_KEY` — without
  one an unreachable internal box means no answer. The chat says *"Internal model
  unreachable — using the cloud model"* and offers to retry. The fallback can
  only happen before the first token; once text is on screen, swapping models
  would splice two models' words into one clinical answer.

  `RoutingEvent.chat_model` now records the model that **answered** rather than
  the one that was requested, alongside a new `model_failed_over` flag.

- **The playground tunes how an answer is worded, not just what it may say.**
  Temperature, reply length and top-p join the retrieval knobs, set by
  `HEAL_TEMPERATURE` (default 0.0), `HEAL_MAX_OUTPUT_TOKENS` (1024) and
  `HEAL_TOP_P` (1.0). They are grouped separately on the screen and in the
  response, because a temperature slider and a score floor do not carry the
  same clinical weight: the floor decides whether a dose may be quoted at all,
  temperature only decides how it reads.

  Every overridden knob now shows the environment line that would make it the
  default for every chat. Tuning a value you cannot keep is half a tool.

  The model picker marks the internal model, so choosing it is a visible choice
  rather than an opaque catalogue id.

### To do

Designed and documented in `docs/architecture-decisions.md`; not yet built.
**Ordered smallest to biggest, and done one at a time.** Dependencies are noted
on the items that have them rather than driving the order.

**Follow-ups the IDF change created** — these are not optional extras; the
change is inert or unvalidated without them:

- **Rebuild the Qdrant collection and re-ingest the corpus.** The IDF modifier
  is fixed at creation, so until this happens the setting is on and doing
  nothing. `/knowledge/status` reports `sparse_idf_needs_reingest` while that is
  the case.
- **Re-derive `HYBRID_ALPHA` and `MIN_RETRIEVAL_SCORE` against IDF scoring.**
  Blocked on the clinician evaluation set (item 19). Until then the floor is
  being applied to a score distribution it was not chosen for, in a direction
  that admits lexical-only matches slightly more readily than before.
- **Consider server-side RRF fusion.** `query_points` can fuse ranks rather than
  magnitudes, which removes the scale mismatch between dense cosine and
  IDF-weighted sparse entirely. Do it after there is something to measure it
  with, not before — it moves the floor again.

1. **Hide the translate button when nothing is behind it.** `TRANSLATION_EN_URL`
   / `TRANSLATION_LUG_URL` default to empty, and the button is offered anyway.
   Report configured-ness to the frontend and render accordingly.
2. **Newer models in the catalogue.** Lines in `_CATALOGUE`
   (`heal/llm/registry.py`); `available_models()` already gates on provider keys
   and the `HEAL_ENABLED_CHAT_MODELS` allowlist.
3. **Corpus stats card content.** The sources-page card states values without
   saying what they mean. Score floor especially: `0.35` alone tells an admin
   nothing about what raising or lowering it does to refusals.
4. **Living idle mark on the new-chat screen.** Reuse `AfricaPulseLoader` on the
   "How can Heal help today?" intro as a resting state rather than a loader:
   much slower, no pulse, no heartbeat — a slow travelling drift like a flag in
   light wind. Same component, second motion mode; keep the
   `prefers-reduced-motion` fallback.
5. **References by title.** Drawer and reference chips lead with the document's
   own title, not a filename or a `source_id:version` slug. `semantic_id`
   already carries `source.label()`; the gap is what `label()` produces and how
   it renders. A gloss-style model call can clean a title as it cleans a
   passage.
6. **Verify citations end to end** against a running stack. Small in code,
   ~25 min in wall clock for the web image. **Items 5, 7 and 9 touch this path
   and should not ship before it passes.**
7. **Star feedback, with comments, minimised.** Five stars replacing thumbs,
   sigmoid aggregate, surfaced to admins as a review signal — deliberately not
   wired into ranking. Optional short comment on the rating. Design target is
   the smallest thing that works: inline, no modal, no card, no heading — it
   must not compete with the answer.
8. **Chat search.** Across a user's own sessions and messages.
9. **Citation provenance — where in the document.** A citation should say where
   the text sits: page, section heading, or at minimum chunk position within
   the source. `chunk_ind` is already stored on the row and shown nowhere.
   Needs ingest to carry section/page into the chunk, so it implies a re-ingest.
10. **Playground generation settings that actually take effect.** Temperature,
    verbosity/length and the rest, plumbed through the same frozen-settings seam
    `RetrievalSettings` uses so nothing mutates global state.
11. **Lock the parameters, and show the standing.** A lock control pinning the
    current parameter set across runs so successive queries are comparable, and
    a summary stating what is in force and how it differs from live defaults.
    Sits on 10.
12. **Self-hosted model base URL.** An admin input for an internal
    OpenAI-compatible endpoint (vLLM), stored as a secret and never rendered
    back. The registry seam exists; this is the config, the storage, and the
    "GPT means the configured model" promise made real.
13. **Answer review + revision back-flow.** Score `addressed` and `readable`;
    below `REVIEW_FLOOR` (0.4), one revision pass that edits the gaps. Never
    regenerate, never revise a refusal, never add uncited clinical content,
    never lose a fact to simplification.
14. **Plain English by default.** Shares the review call with 13, so build them
    together. Same facts, simpler sentences; match the user's register when they
    write clinically. The model is allowed its own words to bridge and explain —
    the rule is that no dose, unit, qualifier or contraindication may be lost,
    not that every sentence must be quoted. An answer that is faithful but
    unreadable has failed a health worker as surely as one that is wrong.
15. **Grounding visibility.** Citation coverage + lexical grounding, shown as
    grounded / partly referenced / general knowledge. Weak answers still shown,
    labelled honestly. Plain counts, no percentages. **Below 5% referenced is a
    defect, not a label**: an answer whose claims are essentially unsupported
    should be flagged to the reader and raised to admins, not quietly badged
    "general knowledge" and shipped.
16. **Luganda translation as a first-class UI surface.** Two explicit entries,
    English→Luganda and Luganda→English, rather than translation existing only
    as a per-message button. Expose the parameters a super admin used to set by
    environment (`TRANSLATION_*`: URLs, timeouts, retries, backoff, stream
    delay) in the admin UI. Extends 1.
17. **Guardrails tracking.** `guardrails-ai` core is Apache-2.0 and, since the
    Aug 2026 hub sunset, validators install straight from public PyPI with no
    account, token or hosted call — so it is usable. Wire selected validators as
    observers on input and output, record every hit as an audit event, surface
    hits in the admin UI. Deterministic validators first; most ML-backed ones
    pull `torch`/`transformers` and break the one-machine, no-GPU constraint.
18. **UUIDs for chat session and message ids.** Needs a migration and touches
    every `chatId` URL; its own pass.
19. **Clinician evaluation set.** Blocks tuning `MIN_RETRIEVAL_SCORE`,
    `REVIEW_FLOOR`, the 5% grounding threshold, and any reranker decision.

**Open, not queued**

- **`docs/architecture-decisions.md` "Advantages" overclaims.** The section
  presents the removed worker fleet, broker, scheduler and search engine as a
  hard-won simplification. Several of those services were unused on this
  workload or were merely optimised, and describing their removal as an
  achievement flatters the decision. The retrieval half of that argument has
  now been corrected in *The IDF gap*; the *Advantages* section itself has not
  been touched, including the line claiming the remaining system "can be held
  in one person's head", which is an argument about our convenience rather than
  about clinical quality.
- **A guardrails framework** for flagging responses that trip a validator.
  Assessed and deliberately deferred as a study exercise — the reasoning, the
  licensing position, what is ruled out and why, is recorded under *Safety
  model*. Presidio for PII detection is the piece worth revisiting first.

### Notes

- The citation path is **not yet verified end to end** against a running stack.
- `MIN_RETRIEVAL_SCORE` is a placeholder (`0.35`) and must be set from measured
  results on a clinician evaluation set before any real deployment. It is a
  clinical-safety parameter, not a tuning knob.
- `PRIVILEGED_ROLE` is currently `ADMIN`, which grants administrators full
  super-admin powers. Tightening it to `SUPER_ADMIN` is one line, and a test
  asserts the current state so the change has to be deliberate.
