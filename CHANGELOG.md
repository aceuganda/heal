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

- **An external reference now says what the body is and where to read it.**
  The drawer told a health worker to "look it up" and then gave them nothing
  to look up with — a bare acronym, no excerpt, no link. That is not an
  instruction anybody can follow if they have not met the acronym before. Six
  bodies Heal expects to see named — the Uganda Ministry of Health, WHO, CDC,
  UNAIDS, UNICEF and NICE — now carry a sentence on what they publish, a note
  on what the reader still has to do once they arrive, and a link to that
  body's own publications library.

  **The warning above it does not move and does not soften.** This sits under
  "Not from the approved library", inside the same amber panel, and the panel
  still says the assistant named the source from general knowledge and that
  nothing was retrieved or checked.

  **These links are not the links the product refuses to print.** The standing
  rule is that a URL the *model* produced is a claim about what sits at the
  other end of it. These are not model output: they are publisher front doors,
  written by hand into `web/src/app/chat/reference/externalSources.ts`,
  reviewable in the diff, and pointing at a library rather than at a document.
  The reader is told where to go and search — not handed a page and told it
  says what the answer said. The panel says so in as many words.

  **A name Heal does not recognise gets no note and no link**, which is the
  correct output rather than a gap: guessing a publisher from an unrecognised
  name is the exact failure this design exists to prevent. The two English
  words in that list are matched as capitalised acronyms only — a source line
  reading "guidance for staff who manage TB" was otherwise filed under WHO.

- **Model settings can now be saved from the admin playground instead of living
  only in environment variables.** Temperature, top-p, the token ceiling, the
  new verbosity level, and the default chat and classifier models can be tuned
  on the playground and then kept with **Save as deployment default** — no
  redeploy, no restart. What an admin saves is what every chat user gets from
  the next message onwards; a health worker does not choose a model, and now an
  operator can.

  **The environment stays the default.** The new `model_settings` table holds
  only the knobs somebody deliberately changed, one nullable column each, and
  a null means "still following the environment". So a deployment can still be
  re-pointed by changing `HEAL_TEMPERATURE` or `HEAL_CHAT_MODEL` without a
  saved value silently overriding it, and clearing a knob on the screen is a
  real operation rather than a guess. The playground shows, per knob, whether
  the value came from the environment or was saved here, who saved it and when.
  A settings change is written to the audit trail: these are not per-request
  values, and "why did the answers get shorter last Tuesday" has to be
  answerable.

  **The retrieval knobs are deliberately not saveable.** The score floor
  decides whether a dose may be quoted at all. It is a clinical-safety
  parameter set from measured results on the eval set, so it stays in the
  deployment's environment where changing it is a reviewed act; the playground
  still tunes it per-run and still prints the env line that would make it
  permanent. Requires a migration (`f3b6d20c47a1`).

- **Verbosity: brief, standard or detailed.** A named answer length rather than
  a token number. Each level puts a length instruction in the prompt, so the
  model writes short instead of being cut off — a token cap does not make a
  model concise, it makes it stop, and the sentence it stops in the middle of
  may be a dose. `HEAL_MAX_OUTPUT_TOKENS` is now what it always really was: a
  hard ceiling. A level may lower it and can never raise it, so an admin who
  capped tokens to control cost has not agreed to more by choosing "detailed".
  Set with `HEAL_VERBOSITY`, default `standard`, overridable from the
  playground.

- **Answers with no approved passage now carry references again.** When the
  library holds nothing on a question, the model closes its answer with the
  standard references a health worker could check — WHO, CDC, the Uganda
  Clinical Guidelines — numbered like any other citation, and each number opens
  the reference drawer.

  **They are marked as what they are, and they are read-only.** An external
  reference is a *name* the model produced, not a passage anybody retrieved, so
  the drawer says "Not from the approved library", shows no excerpt (there is
  no text behind it), offers no link (a URL nobody fetched is a claim about
  what is at the other end), and is never sent for a plain-language gloss —
  summarising a document nobody opened would be invention printed under a
  citation number. The two kinds never share a numbering: when an answer *has*
  approved passages, marker N means passage N and the external block is not
  read at all.

### Fixed

- **Enter on an empty composer sent a blank message and opened a chat with
  it.** The keydown handler only acted when the field had text, so on an empty
  field Enter fell through to the textarea and inserted a newline. `message`
  was then `"\n"` — truthy — so the next Enter sent it: a blank turn to the
  model, and on a fresh page a whole chat session created to hold it.

  Enter now always means "send" and never reaches the textarea, and what
  counts as sendable is `message.trim()`, so a field holding only spaces or
  newlines is empty. One derived value drives the Enter key, the send button's
  disabled state and its colour, so they cannot drift apart. `onSubmit` refuses
  an empty message on its own account too — the session is created *after*
  that check, not before. Shift+Enter still types a line break, and what is
  sent to the model is trimmed.

- **The end of an answer sat jammed against the composer.** The spacer under
  the last message was exactly the composer's height plus 16px, so the final
  line of a clinical answer could be scrolled clear of the input and no
  further. There is 72px of slack now (`SCROLL_PAST_END`), so the list scrolls
  a little past its last line and the end of an answer can be read with room
  under it.

- **Every admin action button crashed the page on the click that started the
  work.** "Upload and index" threw `findDOMNode is not a function` and the
  screen went blank — and so did test search, the playground's Run, **Save as
  deployment default**, and Create user. An admin could not get a document into
  the library at all.

  The cause is the Next 16 move below. Tremor's `Button` runs its `loading`
  state through a `react-transition-group` `Transition` with no `nodeRef`, so
  the first time `loading` flips, the library reaches for `findDOMNode` —
  which React 19 removed. Nothing in Heal called it; the crash sat two
  dependencies deep and only fired on the state change, which is why it
  survived to the admin's first click. Tremor 3.x is deprecated upstream and
  will not fix this, so the busy state is now drawn by
  `web/src/components/LoadingButton.tsx`, which keeps Tremor's styling and
  never passes `loading` down. A test fails the build if a `loading` prop finds
  its way back onto a Tremor `Button`.

  **Worth knowing when reading the code:** `web/package.json` still asks for
  React 18, but Next 16 aliases `react` and `react-dom` to its own bundled
  React 19. The app has been running React 19 since that upgrade regardless of
  what `npm ls` reports, so other React 19 removals may still be waiting in
  dependencies. Aligning the pin with what actually ships is not done here.

- **The safety prompt was talking the assistant out of naming any source.**
  "Do not invent a source, a citation, a guideline name or a statistic" was
  being read as "never name a source", producing answers like *"I cannot
  provide a specific reference or source. However, you can verify… through WHO
  or CDC"* — a refusal and a suggestion in the same breath, and nothing the
  reader could open. The rule now says what it always meant: naming a
  well-known guideline is not inventing one; manufacturing an edition, a page,
  a quotation or a statistic is. Safety prompt version `2026-09-02.1`.

- **The message list is now spaced by the composer's measured height.** The
  spacer under the last message was a pair of fixed min-heights, right for one
  composer state and short for the rest — a grown textarea, the failover
  notice, or the recent-references row put the end of an answer underneath the
  input box. It is measured with a `ResizeObserver` now, so the last line of a
  clinical answer is always readable.

- **Top-p was reported by the playground but never sent to the model.** It was
  resolved, clamped and displayed in the settings panel, and then dropped:
  `build_llm` passed only temperature and the token cap, and the underlying
  client declares a `top_p` attribute that it does not put in the parameters it
  sends. It now travels with the request. Any tuning done against the old
  top-p slider measured nothing.

### Changed

- **Chat history is grouped by calendar day, and every chat says when it was
  started.** The sidebar divided a raw millisecond span by 86,400,000 and
  called anything under 1 "Today" — so a chat started at 23:50 last night sat
  under **Today** for the whole of the next morning, next to one started after
  breakfast, with nothing on either row to tell them apart. Sessions are now
  bucketed by calendar date (**Today**, **Yesterday**, Previous 7 days,
  Previous 30 days, Older), sorted newest-first inside each bucket rather than
  in whatever order the API returned them, and each row carries its start
  time: the clock for today, "Yesterday 23:50" for yesterday, a date beyond
  that, and the year only once it is in doubt. The full timestamp is on hover.

  The time is a caption *under* the row rather than a second line inside it —
  small, italic, and outside the fill that the hover and selected states
  paint. Inside that fill it read as part of the chat's name: two lines of
  equally weighted text in one grey box, which is not what a person scanning
  for a conversation by title wants to read past.

  The grouping moved out of `chat/lib.tsx` into `sessionGrouping.ts` and takes
  `now` as an argument, so the day boundary can be stood on in a test — it
  could not be before, which is why this shipped. The start time is formatted
  in an effect rather than during render: the server and the reader's device
  are in different time zones often enough that an SSR-formatted time would
  hydrate into a different string.

  Also fixed while in there: rename and delete sit inside the link that opens
  the chat, and neither stopped the click, so pressing the bin **navigated to
  that conversation and opened the delete confirmation at once**. And an empty
  sidebar now says so instead of rendering nothing at all.

- **The menu button lines up with the wordmark on a phone.** The header row is
  a 64px flex row with default stretch alignment, and the toggle carries an
  explicit `h-9` — which pins a stretched item to the top of the row rather
  than centring it, leaving the hamburger and close icons sitting well above
  the "Heal" wordmark beside them. It is centred below `sm` and stretches to
  the full row height above it, as it did before.

- **The "add to home screen" prompt is switched off for now.** It is commented
  out at both call sites (sign-in and sign-up) rather than deleted, and the
  component with its per-browser instructions stays in the tree. Uncomment the
  import and the element to bring it back. Offline support went with the PWA
  plugin (below), so what the prompt installs is currently a shortcut to an
  app that still needs a connection.

- **The admin is closed on small screens and says why.** Below 1024px, every
  admin screen now shows "Open the admin on a computer" and a way back to
  chat, instead of a 320px sidebar folded on top of a content column built for
  desktop width. The work these screens exist for — reading retrieval scores
  side by side, comparing a playground run against the score floor, working a
  user table — does not survive one narrow column, and these are the screens
  that set clinical-safety parameters. **This is a block, not a responsive
  layout:** an admin on a phone can no longer reach the library, and that is
  the intended behaviour until the screens are actually designed for it. It is
  a CSS breakpoint rather than a user-agent test, so a small desktop window
  gets the same message, and both branches render server-side so nothing
  flashes the wrong layout.

- **The composer no longer sits on a white slab.** The bar behind the chat
  input was 95% white with a rule along its top, over a page whose actual
  ground is the warm `#f5f4f0` canvas — so it read as a paler panel pasted
  over the bottom of the screen. It is now a gradient of that same canvas
  colour fading up to nothing, with the rule gone: an answer scrolling
  underneath dissolves into the page instead of stopping at a line. The colour
  is a `canvas` token in `tailwind.config.js` now rather than a hex repeated
  per component.

- **The chat input is one field, and it shows when it has focus.** The
  language pills were absolutely positioned over the textarea, paid for with a
  `pt-12` that had to be kept in step by hand — move one without the other and
  the pills landed on the user's first line. Border, background and shadow now
  belong to a wrapper the pills sit inside, so the textarea is transparent and
  the reserved 80px of empty height is gone. **The field also has a focus
  indicator for the first time:** it was `outline-none` with nothing put back,
  so a keyboard user had no way to see where they were. The whole card lights
  up now, which is the shape a user actually sees.

  That last part needs a CSS rule rather than a utility class. `globals.css`
  sets a `:focus-visible` outline for the whole app and is emitted after
  `@tailwind utilities`, so it beats an `outline-none` on the element at equal
  specificity. On a transparent, square-cornered textarea sitting inside a
  rounded card, that outline lands as a hard dark rectangle drawn inside the
  field's own corners. `.heal-composer-input:focus-visible` turns it off for
  that one element — and only because the card around it now carries the
  indicator. **Anything else that suppresses that outline has to put a
  replacement somewhere visible first.** The send button gained
  an accessible name ("Send message" / "Stop generating"), a real 36px hit
  area instead of an svg wearing the styling, and a disabled state that
  matches the greyed-out look it already had.

- **Recent references read as citations again.** The chips ran the marker into
  the title as `[1] Uganda Clinical Guidelines`, and at that size the brackets
  were being read as part of the guideline's name. The marker is a badge now,
  the full title is on hover for the ones that truncate, and the row scrolls
  sideways without a visible scrollbar track under the composer.

- **The splash mark is red now, not teal, and it holds for a second longer.**
  The dot map's palette was 55% teal by dwell time, sitting directly above a
  teal rule under the wordmark — one flat block of the colour, with the logo's
  own red reduced to a passing accent. The weights are inverted: **red now
  holds 85% of the cycle** and black, teal and yellow share the remaining 15%,
  each gone almost as soon as it arrives. The mark is red, crossed now and
  then by a fast band of something else, rather than four colours taking
  turns. The rule under the wordmark still carries the brand teal.

  The hold fraction had to rise with it (0.55 → 0.78). A stop's blend is a
  fraction of the stop being left, so an accent that dwells for 4% of the
  cycle at the old hold would never once show its own colour — it would be a
  smear from red to red by way of something muddy. The two numbers move
  together; a test now pins "red for most of the cycle" so a later reweight
  cannot quietly undo it.

  The splash also holds for 2150ms rather than 1150ms before fading. The
  dot-draw finishes at 780ms, so the previous timing started the fade over a
  mark that had only just landed — the colour band never got to travel across
  the continent once. **This is a second of startup a user now waits through,**
  which is a deliberate trade and the thing to revisit if a field pilot says
  launch feels slow.

- **The chat's waiting state is the splash mark, smaller.** Between sending a
  question and the first token, the answer placeholder now draws the same dot
  continent the app opens with, at 2rem rather than the splash's 5.75rem — a
  health worker sees the mark assemble on launch, and the same continent
  assembling while an answer is prepared reads as the same product thinking
  rather than as a new widget. It needs no loop to stay alive: once assembled
  the mark keeps breathing and the colour band keeps travelling. The rotating
  status lines beside it are unchanged.

  `AfricaPulseLoader`, the loader this replaced, **is still in the tree and
  still works.** It is held for a use not yet chosen, and is marked in its own
  file so it is not swept up as dead code.

- **The web app is off the PWA plugin and on Next 16, and the build is minutes
  faster.** `@ducanh2912/next-pwa` ran a second full webpack pass on every build
  (the duplicated "Compiling for server" line) and had been unmaintained since
  September 2024; it was also the last thing pinning us to webpack. With it gone
  the build runs on Next 16's Turbopack and compiles in seconds. **What a user
  loses: offline support.** The app shell is no longer cached, so a health worker
  who loses connectivity now gets a browser error rather than a cached page — the
  thing to weigh before a field pilot. The install path is mostly intact:
  `manifest.json`, the home-screen icons, and the "add to home screen" prompt all
  stay, and iOS installation never needed a service worker; Chrome on Android may
  no longer offer its native install prompt. `docs/pwa.md` records the options for
  bringing offline back, with Serwist as the maintained successor.
- **Returning visitors get a one-time forced refresh.** Anyone who loaded Heal
  before this change has the old service worker installed, and it would keep
  serving its cached copy of the app forever — pinning them to the last PWA build
  through every future deploy. `web/public/sw.js` is now a hand-written worker
  that clears the caches, unregisters itself, and reloads open tabs. It is source,
  not build output, and must not be deleted until returning visitors have picked
  it up.
- **The web toolchain moved to Node 24.** `web/.nvmrc` pins it and the web
  Dockerfile builds `FROM node:24-alpine`, so local and image toolchains match.
  Node 20 no longer suffices: Next 16 needs 20.9+ and `@capacitor/cli` needs 22+.
  **Anyone building the web app locally needs `nvm use` in `web/` first.**
- **Dependency vulnerabilities dropped from 31 to 21, including both criticals.**
  `sharp` was removed outright — `images: { unoptimized: true }` meant Next never
  called it, so it was carrying four libvips CVEs and a `node-gyp` install script
  for nothing. `js-cookie`, `cookies-next`, and `vitest` were bumped to patched
  releases. Two known items remain: `@capacitor/cli` is on 8.x while the Capacitor
  runtime packages are still on 5.x (a `npm audit fix --force` side effect), and
  Next's own advisory is transitive through `postcss`.

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
- **Cited-passage ids are UUIDs.** `search_doc.id` reaches the browser in a
  message's citation map and is taken off the URL by
  `GET /chat/reference/{id}/gloss`. That handler authenticates the caller but
  does not check the row belongs to them, so a sequential id could be walked to
  read every cited guideline passage in the deployment. Migration `d4a2b8e15f97`
  makes the id unguessable. **The missing ownership check remains open** — a
  UUID stops enumeration, it does not make the handler authorise. What is
  reachable is approved guideline text, never patient data, questions or answers.

  **Citation maps on existing messages are cleared.** They hold integer ids that
  no longer resolve. Rewriting them meant a correlated join through
  `jsonb_each_text`, which fails outright on any row whose `citations` is a JSON
  scalar or `null` rather than an object — and real rows are. Clearing is one
  statement that cannot fail on malformed JSON; the cost is that markers in old
  answers render as plain text, which is already what the UI does with a
  citation it cannot resolve. New answers are unaffected.

- **Chat session ids are UUIDs.** The session id is the one identifier that
  reaches a URL (`/chat?chatId=...`), and a sequential one told anyone who saw
  it how much the deployment was being used and let them probe for sessions that
  exist. It matters most where auth is disabled: ownership is then
  `user_id IS NULL` for everyone, so a guessable id was the only thing between
  one anonymous visitor and another's conversation.

  Message ids stay sequential — they never appear in a URL and are only reached
  through a session whose ownership has already been checked.

  Migration `c8f1a24b7e63` mints a UUID per session and carries it into
  `chat_message.chat_session_id` through a join on the old integer, so existing
  conversations keep their messages. The old integer is not preserved: a stale
  sequential id lying around is what this removes. **The downgrade re-numbers
  sessions from a fresh sequence, so every existing UUID URL dies** — it exists
  to unblock a local rollback, not for data anybody cares about.

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
7. ~~**Star feedback, with comments, minimised.**~~ **Done** — shipped as a
   four-point rating rather than five (an even scale has no neutral middle to
   hide in). Aggregate, admin endpoints and the inline control are in; the
   remaining piece is an admin *screen* over `/manage/feedback/answers` and
   `/manage/feedback/sources`, which currently return JSON only.
8. **Chat search.** Across a user's own sessions and messages.
9. **Citation provenance — where in the document.** A citation should say where
   the text sits: page, section heading, or at minimum chunk position within
   the source. `chunk_ind` is already stored on the row and shown nowhere.
   Needs ingest to carry section/page into the chunk, so it implies a re-ingest.
10. ~~**Playground generation settings that actually take effect.**~~ **Done** —
    temperature, reply length and top-p travel as a `GenerationSettings` value
    through the same frozen-settings seam `RetrievalSettings` uses, and each
    overridden knob shows the environment line that would make it the default.
11. **Lock the parameters, and show the standing.** A lock control pinning the
    current parameter set across runs so successive queries are comparable, and
    a summary stating what is in force and how it differs from live defaults.
    Sits on 10.
12. ~~**Self-hosted model base URL.**~~ **Done, with the design changed.** The
    endpoint is operator configuration (`HEAL_SELF_HOSTED_URL` and three
    siblings), **not** an admin input. A server that fetches a URL a caller
    supplied is server-side request forgery: it will read the cloud metadata
    endpoint or port-scan the internal network on the caller's behalf, and hand
    back the results. The URL is never accepted from a request and never sent to
    the browser. Unreachable after two tries, the cloud model answers and the
    audit records which model actually did.
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
20. **Make the production API image small enough to deploy reliably.** A first
    read of `requirements/default.txt` says the roughly 3 GB is mostly dead
    weight, and that the service split is the *last* lever to reach for, not
    the first:

    - `tensorflow==2.14.0` is imported in exactly one file,
      `heal_app/search/search_nlp_models.py`, which is legacy Danswer search
      reachable only from the removed Vespa index, the Slack bot and
      `one_shot_answer`. Importing `heal_app.main` loads neither TensorFlow,
      torch, nltk nor sentence-transformers, so the API boots without touching
      any of it.
    - `torchvision==0.15.2` has no references anywhere in `heal/`, `heal_app/`
      or `shared_models/`.
    - `torch==2.0.1` comes from the default PyPI index, so the Linux wheel
      drags in the bundled NVIDIA CUDA libraries — well over a gigabyte that
      never executes on a CPU deployment. The CPU wheel index is a one-line
      change.

    Do those three and measure again before designing anything. A multi-stage
    builder is worth having but is close to a rounding error here: it removes
    `cmake` and the apt lists, while every runtime wheel still has to be copied
    into the final image.

    **The split is also less available than it looks.** torch cannot leave the
    API image today: `heal/knowledge/embedder.py` loads the sentence-transformer
    lazily, but *query* embedding is on the request path, so the API needs the
    model even if all ingestion moves elsewhere. Moving extraction and OCR out
    is real; moving embedding out means putting query embedding behind a
    network call, which is a larger decision than image size alone justifies.
    None of this is a runtime problem — 3 GB costs pull time, registry storage
    and host disk, not request latency. Keep any indexer compatible with the
    same approved-source and Qdrant workflow, and document the operational
    trade-off before introducing a permanently running worker.

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
