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

### Notes

- The citation path is **not yet verified end to end** against a running stack.
- `MIN_RETRIEVAL_SCORE` is a placeholder (`0.35`) and must be set from measured
  results on a clinician evaluation set before any real deployment. It is a
  clinical-safety parameter, not a tuning knob.
- `PRIVILEGED_ROLE` is currently `ADMIN`, which grants administrators full
  super-admin powers. Tightening it to `SUPER_ADMIN` is one line, and a test
  asserts the current state so the change has to be deliberate.
