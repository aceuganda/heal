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
- **Duplicate React keys on reference chips.** They were keyed by
  `document_id`, which is `source_id:version` and therefore shared by every
  passage from one guideline. Two citations from the same source collided.
- **Reference glosses were generated twice.** The drawer's content component is
  mounted twice — once for the desktop panel, once for the mobile sheet, with
  only CSS deciding which is visible — so fetching inside it ran two model calls
  per opened citation.

### To do

Designed and documented in `docs/architecture-decisions.md`; not yet built.

1. **Verify citations end to end** against a running stack. Nothing below is
   worth layering on an unverified path.
2. **Answer review + revision back-flow.** Score `addressed` and `readable`;
   below `REVIEW_FLOOR` (0.4), one revision pass that edits the gaps. Never
   regenerate, never revise a refusal, never add uncited clinical content,
   never lose a fact to simplification.
3. **Plain English by default.** Same facts, simpler sentences; match the
   user's register when they write clinically.
4. **Grounding visibility.** Citation coverage + lexical grounding, shown as
   grounded / partly referenced / general knowledge. Weak answers still shown,
   labelled honestly. Plain counts, no percentages.
5. **Star feedback.** Five stars replacing thumbs, sigmoid aggregate, surfaced
   to admins as a review signal — deliberately not wired into ranking.
6. **UUIDs for chat session and message ids.** Needs a migration and touches
   every `chatId` URL; do it as its own pass.
7. **Clinician evaluation set.** Blocks tuning `MIN_RETRIEVAL_SCORE`,
   `REVIEW_FLOOR`, and any reranker decision.

### Notes

- The citation path is **not yet verified end to end** against a running stack.
- `MIN_RETRIEVAL_SCORE` is a placeholder (`0.35`) and must be set from measured
  results on a clinician evaluation set before any real deployment. It is a
  clinical-safety parameter, not a tuning knob.
- `PRIVILEGED_ROLE` is currently `ADMIN`, which grants administrators full
  super-admin powers. Tightening it to `SUPER_ADMIN` is one line, and a test
  asserts the current state so the change has to be deliberate.
