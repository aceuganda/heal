# Heal: architecture

**Revised:** 2026-09-01
**Scope:** what the system is, how a question becomes an answer, why it is
shaped this way, and what that shape costs.
**Companion:** `docs/runtime-architecture.md` — the services and the code
holding each one in place.

Heal answers clinical questions for health workers, in English and Luganda,
grounded in an approved library of medical references. An answer either cites
an approved source or says plainly that it has none.

The system began as a fork of Danswer, an enterprise document-search product.
Most of this document explains the difference between what that product was
built to do and what Heal needs to do. That difference is not a judgement about
the original — it was a good fit for its own problem — but the two problems are
not the same one, and the architecture had to change to match.

> **Package naming.** The live application package is `backend/heal_app/`
> (formerly `backend/danswer/`). Some inherited modules under `deprecated/` and
> some file paths in the git history still use the old name.

---

## Contents

- [What runs](#what-runs)
- [How a question becomes an answer](#how-a-question-becomes-an-answer)
- [The decisions that shape everything else](#the-decisions-that-shape-everything-else)
- [Understanding the question](#understanding-the-question)
- [Retrieval and ranking: before and after](#retrieval-and-ranking-before-and-after)
- [Language](#language)
- [Safety model](#safety-model)
- [Answer review and revision](#answer-review-and-revision)
- [Citations and grounding](#citations-and-grounding)
- [Feedback](#feedback)
- [Ingest](#ingest)
- [Schema and migrations](#schema-and-migrations)
- [What used to run in the background](#what-used-to-run-in-the-background)
- [Advantages](#advantages)
- [Limitations and risks](#limitations-and-risks)
- [Capacity](#capacity)
- [Reference material](#reference-material)

---

## What runs

Five services. `make up` starts all of them; there is no second command and no
opt-in profile.

| Service | Image | Role |
| --- | --- | --- |
| `api_server` | `heal-backend` | FastAPI. Chat, retrieval, admin, auth. Streams answers over SSE. |
| `web_server` | `heal-web` | Next.js 14. Chat UI, admin UI, PWA/Capacitor shell. |
| `relational_db` | `postgres:15.2-alpine` | System of record: users, chats, messages, sources, chunks, feedback. |
| `qdrant` | `qdrant/qdrant:v1.19.0` | Vector index. Derived data — rebuildable from PostgreSQL. |
| `nginx` | `nginx:1.23.4-alpine` | Single front door; long read timeout for indexing requests. |

The embedding model (`thenlper/gte-small`, 384 dimensions, ~64 MB) is baked
into the backend image at `/opt/models` and loaded in-process. There is no GPU,
no model server, no inference fleet, and no background worker of any kind.

---

## How a question becomes an answer

### The inherited path

```text
                     Browser / PWA / Capacitor shell
                                  |
                                  v
                        Next.js 14  (web/src/app)
                     chat/  search/  admin/  auth/
                                  |  POST /chat/send-message  (SSE)
                                  v
    ==========================  FastAPI api_server  ==========================
    danswer/chat/process_message.py :: stream_chat_message        (543 lines)
    |
    |-- 1. is_luganda?  --> translate_to_english(text)
    |                        utils/translation.py
    |                        plain HTTP, hard-coded IP, no auth, no timeout
    |
    |-- 2. persist user message                    -> PostgreSQL
    |
    |-- 3. run_search?  -> check_if_need_search()  -> LLM round trip #1
    |
    |-- 4. history_based_query_rephrase()          -> LLM round trip #2
    |
    |-- 5. retrieval_preprocessing()
    |        -> query_intent()  TFDistilBert "danswer/intent-model"
    |             3 classes: keyword | semantic | QA
    |        -> filter extraction, ACL, time cutoff
    |
    |-- 6. full_chunk_search_generator()           -> VespaIndex
    |        embed query   -> gte-small (384d)     model_server / local torch
    |        search        -> Vespa 8.277.17       BM25 + vector, HYBRID_ALPHA
    |        rerank        -> 2x English MS MARCO cross-encoders
    |
    |-- 7. LLM chunk filter                        -> LLM round trip #3
    |
    |-- 8. generate_ai_chat_response()             -> gpt-3.5-turbo
    |
    |-- 9. is_luganda? --> translate_to_luganda()
    |
    '-- 10. persist assistant message + citations  -> PostgreSQL
    ==========================================================================

    Supporting services:
      api_server | background (Celery+Beat+Dask+Supervisor) | web_server
      postgres | vespa | nginx | optional model_server

    Python weight: torch, tensorflow, transformers, sentence-transformers,
      nltk, dask, celery, supervisor, llama-index, langchain, playwright,
      + ~20 connector SDKs
```

Three properties of that flow drove the redesign:

1. **It is one function.** Steps 1–10 are inline branches in a single 543-line
   function. Nothing in it could be tested without Vespa running.
2. **Every branch exists to tune one search engine.** `SearchType`, `QueryFlow`,
   the intent model, the rerankers and the chunk filter are all controls for
   Vespa. They are the right controls for a product whose job is *search across
   many heterogeneous corpora*. Heal has one curated corpus.
3. **Luganda was already translated away at step 1.** The retrieval stack never
   saw a Luganda token. The current design formalises what the code already did.

### The current path

```text
                     Browser / PWA / Capacitor shell
                                  |
                                  v
                        Next.js 14  (web/src/app)
                          chat/  admin/  auth/
                                  |  POST /chat/send-message  (SSE)
                                  v
    ============================  FastAPI Heal API  ==========================

    heal/medical_guidance/  MedicalGuidanceAgent          <-- the only agent
    |
    |-- 1. LanguageService.to_english(text)     if the session is Luganda
    |        heal/language/providers/heal_mt.py
    |        env-configured URLs, timeout, retry, optional bearer token
    |
    |-- 2. persist user message (original + English)      -> PostgreSQL
    |
    |-- 3. understand(text_en, history)         -> ONE structured LLM call
    |        label      EMERGENCY | DOSAGE_OR_MEDICATION | CLINICAL_QUESTION
    |                   GENERAL_HEALTH_INFO | ADMIN_OR_SMALLTALK | OUT_OF_SCOPE
    |        query      the question rewritten for retrieval: grammar and
    |                   spelling repaired, references resolved, abbreviations
    |                   expanded, one specific clinical question
    |        terms      clinical identifiers to preserve verbatim
    |                   ("TDF/3TC/DTG", "500mg BD")
    |        original   the user's own words, kept unchanged
    |
    |-- 4. route_for(label)                     -> fixed table, not model-chosen
    |        EMERGENCY            -> escalation copy FIRST, then answer
    |        DOSAGE_OR_MEDICATION -> retrieval REQUIRED; refuse if no source
    |        CLINICAL_QUESTION    -> retrieve + cite
    |        GENERAL_HEALTH_INFO  -> retrieve if available
    |        ADMIN_OR_SMALLTALK   -> no retrieval, no citation
    |        OUT_OF_SCOPE         -> decline + redirect, stop
    |
    |-- 5. KnowledgeStore.search(query, original, k)      heal/knowledge/
    |        embed the REWRITTEN query  -> gte-small, in-process (384d)
    |        build the sparse vector from rewritten + ORIGINAL, so a code the
    |          user typed still matches even if the rewrite dropped it
    |        PRE-filter     -> approved AND current version  (Qdrant payload
    |                          filter, applied BEFORE the ANN search)
    |        hybrid rank    -> dense cosine + sparse lexical, fused
    |        score floor    -> below MIN_RETRIEVAL_SCORE, return nothing
    |        diversity cap  -> max N chunks per source document
    |
    |-- 6. PromptBuilder.build()
    |        versioned safety instruction + history + approved context
    |
    |-- 7. LLM stream                                     heal/llm/
    |        StreamProcessor accumulates the answer
    |
    |-- 8. review(question, answer, passages)             heal/medical_guidance/
    |        coverage  how much of the answer rests on a cited passage
    |        addressed did it actually answer what was asked (0..1)
    |        readable  is it plain English at the question's own level (0..1)
    |        gaps      what is missing, in words
    |        |
    |        '-- if addressed < REVIEW_FLOOR (0.4): ONE revision pass that
    |            EDITS THE GAPS. Not a regeneration -- the answer that exists
    |            is kept and the holes in it are filled, so a good paragraph
    |            is never thrown away to fix a missing one.
    |
    |-- 9. LanguageService.to_luganda(answer)   if the session is Luganda
    |
    '-- 10. persist message + cited passages + grounding + audit -> PostgreSQL
    ==========================================================================

    Removed from the runtime path: Vespa, Celery, Beat, Dask, Supervisor,
      the Slack listener, connector polling, the model-server fleet,
      TensorFlow, the English rerankers, the LLM chunk filter, the query
      rephrase step, and the enterprise search UI.
```

**Three LLM round trips became one.** The old flow spent three secondary calls
(`check_if_need_search`, rephrase, chunk filter) deciding *how* to search before
it answered anything. The current flow makes one classification call, then
answers. That is lower latency and lower cost, but the reason it matters most is
auditability: one recorded decision with a label and a route, rather than three
opaque judgements.

**Retrieval is a direct call, not a tool.** The model never decides whether to
search. The route table decides, deterministically, before the model runs. This
is the single most important structural difference, and everything in the safety
model rests on it.

---

## The decisions that shape everything else

These are settled. Anything elsewhere that contradicts them is a bug in the
document, not in the code.

| # | Decision | Consequence |
| --- | --- | --- |
| D1 | **Qdrant is the vector store. PostgreSQL is the system of record.** | The index is derived data and can be rebuilt. pgvector is a documented fallback only; never run both for one collection. |
| D2 | **Translate, then retrieve.** Luganda in → English → retrieve in English → answer in English → Luganda out. | The corpus and the embedding model are English-only. Luganda quality becomes a translation problem — testable and fixable — rather than a retrieval problem. |
| D3 | **One agent module,** `MedicalGuidanceAgent`. Retrieval only. | No tool loop, no planner, no agent selector, no multi-agent handoff, no autonomous background task. |
| D4 | **Understanding the question is one step that serves two masters:** safety routing *and* retrieval quality. | Six medical labels drive a fixed route table, and the same call produces the cleaned, specific query that retrieval actually searches on. What is retired is the *search-mode switch* — keyword vs semantic vs QA — not the idea that knowing the question helps you find the answer. |
| D5 | **Retired code moves to `deprecated/`, it is not deleted.** | Reviewable and revertable. Nothing under `deprecated/` may be imported, registered, or collected by lint, type-check or tests. A CI grep enforces it. |
| D6 | **384-dimension embeddings, one in-process embedder, no reranker.** | The dimension is frozen. Changing it means a new collection and a full re-embed, so it is asserted against the model at startup rather than trusted. |
| D7 | **No background workers.** | Nothing is time-triggered. Every ingest run has a human actor recorded against it. |

### Where the swap points are

The architecture is deliberately narrow at four seams, so that the expensive
decisions stay reversible:

- `KnowledgeStore` — the retrieval interface. Replacing Qdrant with pgvector is
  one file.
- `heal/llm/registry.py` — a catalogue of chat models. `gpt-4o-mini` is the
  default; `gpt-4o`, `gpt-3.5-turbo` and `claude-sonnet-4-5` are registered, and
  a model is only offered if its provider has a key in the environment.
  Changing model is configuration, not a code edit.
- `heal/language/providers/` — the translation provider. `heal_mt` (the private
  MT pair) is the current implementation; another can be registered without
  touching a call site.
- `heal/medical_guidance/routes.py` — the route table. Changing what an intent
  does is a reviewed code change, never a runtime or model decision.

---

## Understanding the question

Retrieval can only find what the query describes. A health worker typing on a
phone, in a hurry, in their second language, does not produce a well-formed
search query — and the inherited system's answer to that was three separate LLM
round trips before it answered anything. Heal does it in one call, and uses the
result for two different jobs.

```text
  "wat z the dose of TDF/3TC/DTG for a 14yr old, she weighs 40kg"
        |
        v
  understand(message, history)          heal/medical_guidance/
        |                                ONE structured call to the configured
        |                                model (see "Where the swap points are"
        |                                — the provider is replaceable)
        v
  label     DOSAGE_OR_MEDICATION        -> the route table (safety)
  query     "dolutegravir-based ART     -> what retrieval embeds
             regimen dosing for an
             adolescent weighing 40 kg"
  terms     ["TDF/3TC/DTG", "40kg"]     -> preserved verbatim for lexical match
  original  the user's own words        -> kept, and shown to the model
```

### Why one call and not two

The obvious design is a grammar-fixing stage followed by a classifier. It is
worse. The two tasks need exactly the same input — the message plus enough
history to resolve what "she" refers to — and reading that input twice doubles
the latency a health worker waits through before anything happens, doubles the
cost, and creates a class of bug where the two stages disagree about what was
asked. One structured response carries both.

### What the rewrite is allowed to do

- Repair spelling, grammar and phone-keyboard noise.
- Resolve references from the history: "and for a child?" becomes a question
  that means something on its own.
- Expand abbreviations that are ambiguous out of context.
- State the question specifically, in the vocabulary a clinical guideline would
  use rather than the vocabulary the user happened to reach for.

### What it must not do

- **It must not answer the question.** It produces a query, never content.
- **It must not invent clinical detail.** A weight, an age or a drug that was
  not in the message cannot appear in the rewrite. This is the failure that
  would matter: a rewrite that adds "paediatric" to a question about an adult
  retrieves the wrong guideline, and the answer is then correctly cited and
  wrong.
- **It must not discard the original.** The user's own words are kept and go
  into the prompt alongside the rewrite, so the model answering can see what
  was actually typed.

### Why the original text still reaches retrieval

The dense half of the search embeds the rewritten query, because that is the
version phrased like the guideline it needs to match. The **sparse half is built
from the rewrite and the original together.** If a health worker types
`TDF/3TC/DTG` and the rewrite generalises it to "dolutegravir-based regimen",
the lexical vector still carries the exact code, so the chunk containing that
code still matches. Losing an exact drug-code match to a tidier query would be a
self-inflicted wound in precisely the place this product cannot afford one.

### When it fails

Like classification, it degrades rather than raising. If the call fails or
returns something unusable, the label falls back to `CLINICAL_QUESTION` and the
search query falls back to the user's original text. That is exactly the
behaviour the system had before this stage existed, so a bad day for the model
costs retrieval quality, not the answer.

Every rewrite is recorded in the audit event alongside the label — the rewritten
query only, never the patient-identifying free text of the original.

---

## Retrieval and ranking: before and after

This is the part of the inherited system with the most machinery and the least
documentation, so it is set out explicitly.

### What ranked results before — six stages

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
       2x English MS MARCO cross-encoders
       ensemble average -> min-shift
       x boosts  x recency_multiplier -> normalize -> sort
    |
 [4] chunk.boost                              document_index_utils.py:11
       admin/crowd document feedback -> integer
       sigmoid curve -> 0.5x .. 2.0x score multiplier
    |
 [5] filter_chunks()  LLM relevance filter
       one more LLM round trip; yields list[bool]
    |
 [6] map_document_id_order()
       fixes citation numbering from final order
    |
  chunks fed to the LLM
```

### What ranks results now — five stages

```text
  english query
    |
 [1] PRE-filter in Qdrant   (payload filter, applied before the ANN search)
       approved == true  AND  source version is current
       It must be a Qdrant filter, not a post-search drop: post-filtering an
       HNSW result set silently returns fewer than k and hides the loss.
    |
 [2] HYBRID SCORE                          <-- the primary rank
       dense cosine (gte-small, 384d)  fused with
       sparse lexical (hashed term frequency, sublinear damping)
       HYBRID_ALPHA = 0.6 weights the dense half
    |
 [3] SCORE FLOOR                           <-- new; the old system had none
       below MIN_RETRIEVAL_SCORE -> return nothing, and the agent says it has
       no approved source rather than citing weak text
    |
 [4] per-source diversity cap
       max N chunks per source document, so one long guideline cannot crowd
       out a corroborating second source
    |
 [5] context ordering + citation numbering
       final order sets prompt position and the [n] a reader clicks
    |
  chunks -> PromptBuilder
```

### Stage by stage

| Old stage | Status | Reasoning |
| --- | --- | --- |
| Hybrid BM25 + vector | **kept, reimplemented** | Lexical matching is not optional for this product — `TDF/3TC/DTG` and `500mg BD` must match exactly. Vespa's BM25 was replaced with Qdrant sparse vectors: same capability, no second service. |
| Keyword / semantic mode switch | dropped | One collection, one model. There is nothing to switch between, and `SearchType` has no meaning. |
| Recency decay | **replaced with explicit versioning** | A curated library of approved clinical guidance should not silently prefer newer text. Supersession is a fact, not a gradient: a source version is approved or it is not. |
| Cross-encoder reranking | **deferred** | Not forbidden — see the trigger below. |
| Crowd/admin `boost` sigmoid (0.5×–2.0×) | **removed, not replaced** | An unaudited multiplier that silently reweights clinical sources is a control Heal should not have. If reweighting is ever needed it will be admin-set, versioned and logged. |
| LLM relevance filter | dropped | An extra LLM round trip per query. The score floor does most of that job with no latency. |
| Citation ordering | kept | Same job, same need. |
| — | **score floor is new** | The old pipeline always returned top-k regardless of quality. For a dosage question, citing a weak match is worse than refusing. |

**What was genuinely given up.** Vespa is a more capable search engine than
Qdrant plus a hash-based sparse vector. It offers real BM25 with corpus
statistics, richer query expressions, and tuning this system cannot express.
For a few thousand chunks of curated clinical text the difference is unlikely to
matter — but this has not been measured on Heal's own corpus, and "unlikely"
is not "shown". See *Limitations*.

### Constants, and which one matters

| Constant | Default | Purpose |
| --- | --- | --- |
| `RETRIEVAL_TOP_K` | 20 | candidates fetched from Qdrant |
| `CONTEXT_TOP_K` | 5 | chunks placed in the prompt |
| `MAX_CHUNKS_PER_SOURCE` | 2 | diversity cap |
| `HYBRID_ALPHA` | 0.6 | weight of the dense half of the score |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 1200 / 200 chars | chunk boundaries |
| `MIN_RETRIEVAL_SCORE` | **0.35 — a placeholder** | the score floor |

`MIN_RETRIEVAL_SCORE` is a clinical-safety parameter, not a tuning knob. Too low
and the agent cites irrelevant text under a marker that lends it false
authority; too high and it refuses questions it could have answered. **The
current value is a guess and is marked as one in the code.** It must be set from
measured results on a clinician evaluation set, and the value and the evidence
recorded here.

### Reranking: what it is for, and why there isn't one

**Why reranking matters.** Embedding search is a compromise made for speed. A
query and a chunk are each crushed into 384 numbers *independently*, and the
score is the angle between them. Nothing in that computation ever looks at the
query and the chunk together. That is what makes it fast enough to search
thousands of chunks in milliseconds, and it is also its ceiling: a passage that
mentions the right drug, the right condition and the right age band scores well
whether or not it actually answers the question, because "aboutness" is most of
what a single vector can carry.

A cross-encoder reranker removes that compromise for a handful of candidates. It
reads the query and one chunk *together* and scores the pair directly, so it can
tell "the paediatric dose is 5mg/kg" from "paediatric dosing is discussed in
section 4". For a clinical product that distinction is the whole game: the two
passages are nearly identical to an embedding and completely different to a
health worker. Reranking is the standard fix for the standard failure — the
right passage is retrieved, but ranked fourth, and only the top three reach the
prompt.

**Why there isn't one.** Three reasons, in order of weight:

1. **It has nothing to improve yet.** A reranker reorders candidates. At the
   target corpus — around a hundred documents, a few thousand chunks — a query
   often has only a handful of genuinely relevant chunks in the whole library.
   Reordering five candidates of which two are relevant is not where the quality
   is won. The score floor and the approved-source filter are doing more work
   than a reranker would.
2. **The cost lands on every question.** A cross-encoder scores pairs one at a
   time, so latency and CPU grow with the number of candidates. That is a
   permanent tax on every health worker's wait, paid to fix a failure that has
   not yet been shown to occur.
3. **It is unvalidated here.** The available cross-encoders
   (`ms-marco-MiniLM`-family) are trained on web search relevance, not clinical
   guidance. "Relevant" in MS MARCO and "safe to cite for a dose" are not the
   same judgement, and adopting one without measurement would add a confident
   reordering step nobody has checked.

Point 3 deserves more than a line, because it is the one that would cause harm
rather than merely waste effort.

MS MARCO is a dataset of web search queries paired with passages a human found
useful. A model trained on it learns what *satisfies a searcher*: passages that
are direct, self-contained, confidently worded, and topically on the nose. Those
are good instincts for a search engine and subtly wrong ones for clinical
guidance, where the passage that should be cited is often the least satisfying
one on the page — hedged, full of qualifiers, pointing at a table, and correct
precisely because of the hedging.

The concrete failure is a reordering that prefers the confident passage over the
qualified one. A guideline saying "give 5mg/kg" reads as a better answer than one
saying "give 5mg/kg in children over 3 months with normal renal function; see
Table 4 for adjustment" — and the second is the one a health worker needs. A
reranker trained to maximise searcher satisfaction has been trained, in effect,
to strip the caveat. Nothing in the score it returns would reveal that it had
done so.

This is worse than no reranker for a specific reason: it fails *silently and
confidently*. Dense retrieval's weakness is legible — a wrong passage scores
close to a right one and the score floor can be tuned against it. A reranker
overrides that ordering with a number derived from a judgement nobody has
inspected, so a bad reordering looks exactly like a good one from the outside.
Adding an opaque authority over which passage a health worker gets shown, on the
strength of "rerankers usually help", is not a trade this product should make
without evidence.

**What validating one would actually require** — worth writing down, because
"we'll evaluate it" is how this gets waved through:

- The same held-out clinician-labelled set used for everything else, with the
  correct chunk marked per question, not a general relevance judgement.
- Measured against the incumbent, offline, on the *same* candidate sets — the
  question is whether reordering helps, not whether retrieval works.
- Deliberate coverage of the hedged-versus-confident case above, since that is
  the specific way this class of model is expected to fail here.
- Latency measured at the real `RETRIEVAL_TOP_K`, not in isolation, because the
  cost is per-question and permanent.

If it clears that, adopt it. If nobody has time to run it, that is an answer
too, and the answer is no.

Note what is *not* on that list: language. Because translation happens upstream,
a reranker would receive an English query, so the inherited English
cross-encoders are perfectly usable candidates. They are deferred on cost and
evidence, not on capability.

**The trigger to add one is specific,** and worth writing down now so it is not
argued about later: the evaluation set shows the correct chunk retrieved inside
the top 20 but not inside the top 5.

The reasoning behind that shape is worth spelling out, because it is a
diagnostic and not a threshold. Retrieval fetches `RETRIEVAL_TOP_K` (20)
candidates and the prompt receives `CONTEXT_TOP_K` (5). So there are exactly
three things that can go wrong, and only one of them is a ranking problem:

| What the evaluation shows | What it means | What fixes it |
| --- | --- | --- |
| Correct chunk in the top 5 | Retrieval is working | Nothing — look at the prompt or the answer |
| Correct chunk in the top 20, not the top 5 | **Found but mis-ordered** | A reranker. This is the only case it addresses |
| Correct chunk not in the top 20 at all | Never found | Chunking, translation, or the library does not contain it |

The third row is the one that matters most, and it is where a reranker does
active harm. A reranker cannot promote a candidate that was never fetched — it
only reorders what retrieval already returned. So if the correct passage is
missing entirely, adding a reranker changes the top 5 to a *different* set of
wrong passages, and the aggregate score often improves slightly, because the
reordering does help the questions that were already nearly right. The
underlying failure — a badly chunked guideline, a mistranslated query, a source
nobody uploaded — is now buried under a metric that moved in the right
direction. That is the expensive kind of wrong: real money and latency spent
making a diagnostic harder to read.

So the order is: measure where the correct chunk actually lands *before*
reaching for a reranker. If it is missing from the candidate set, fix the thing
that lost it. Reranking is the last intervention, not the first, and the
cheaper ones — chunk boundaries, `HYBRID_ALPHA`, a stronger 384-dimension
embedding model — are all reversible in a way a permanent per-question latency
cost is not.

---

## Language

```text
   Luganda query
        |
        v
   LanguageService.to_english()        private MT service, env-configured
        |
        v
   English query --------> English embedding --------> Qdrant (English chunks)
        |                                                    |
        v                                                    v
   English answer <---- LLM (+ approved English context, citations)
        |
        v
   LanguageService.to_luganda()
        |
        v
   Luganda answer  +  citations rendered from PostgreSQL source metadata
```

**Why translate rather than embed Luganda directly.** The short answer is that
this is not a live question, and the section exists so it is not re-opened
casually.

Direct Luganda retrieval is not a component that can be swapped in. The
multilingual retrieval models usually reached for — the `multilingual-e5`
family, `BAAI/bge-m3` — are built on XLM-RoBERTa, whose pretraining language
list does not appear to include Luganda, so they would buy coverage of
languages Heal does not serve at several times the model weight, without
actually solving the language it does serve. Genuine Luganda retrieval would
mean AfroXLMR-family encoders fine-tuned for the task: a research effort with
its own data collection, not an afternoon's configuration change.

**What has to be true before this is even worth costing.** The current design
has not yet been measured. Nobody has established how much retrieval quality
the translation hop costs, because there is no evaluation set to measure it
with. Until that exists, "embed Luganda directly" is a solution to a problem of
unknown size — and the far more likely finding is that translation quality, not
embedding language, is where the loss actually is. That is also the cheaper
thing to fix.

So the order is: build the English↔Luganda medical-phrase test set, measure
where answers actually degrade, and only then ask whether the corpus language is
the constraint. Verify the XLM-R language list on the model cards before anyone
re-opens this on the strength of a model name.

Consequences to hold onto:

- The corpus is stored and embedded in **English**. A source that arrives in
  Luganda is translated at ingest, and both versions are kept in PostgreSQL —
  the English one is what gets embedded.
- **Translation quality is on the clinical critical path.** It needs its own
  English↔Luganda medical-phrase test set covering drug names, dosage units,
  negation and uncertainty.
- A Luganda reader sees Luganda answer text with English source titles, because
  citations render from stored metadata. Source titles are deliberately not
  machine-translated.

The translation services were the single worst thing in the inherited codebase:
plain HTTP to hard-coded public IP addresses, no authentication, no timeout, no
failure path. A hung MT service hung the entire chat request. They are now
reached through a provider interface with URLs from the environment, connect and
read timeouts, bounded retries on connection failures only, and an optional
bearer token. Retries never replay a partially streamed response, because
replaying one would duplicate text in a reader's answer.

---

## Safety model

The safety properties are structural — they come from where decisions are made,
not from asking the model to behave.

1. **The model never chooses to search.** A fixed table maps intent to route.
2. **A dosage question with no approved source is refused,** not answered from
   the model's own knowledge. The refusal names its reason, because "the library
   is unreachable" and "nothing approved covers this" call for different actions
   from someone standing in front of a patient.
3. **Emergency escalation is emitted before the model is called,** so it reaches
   the reader even if generation is slow or fails outright.
4. **The safety instruction is versioned** (`SAFETY_PROMPT_VERSION`) and written
   into the audit event, so any answer can be traced to the rules that produced
   it.
5. **Audit events carry no patient text** — only ids, labels, model versions and
   outcomes. That is what makes them safe to ship to ordinary log storage.
6. **Retrieval failure degrades, it never 500s.** An unreachable store returns an
   outcome flagged `unavailable`, and the agent explains itself.

Access control is three roles — `SUPER_ADMIN`, `ADMIN`, `MEMBER` — checked by
rank, never by equality. The first account created in an empty database becomes
`SUPER_ADMIN`; everyone else, including all self-registration, becomes `MEMBER`.
The last super admin cannot be demoted.

---

## Answer review and revision

An answer that streams cleanly can still miss the question. The review step runs
after generation and before the answer is finalised, and it asks two separate
questions that are easy to confuse:

| Question | What it measures | What it drives |
| --- | --- | --- |
| **Was it answered?** | Does the text address what was actually asked, including every part of a multi-part question | Whether a revision pass runs |
| **Was it grounded?** | How much of the answer rests on a cited approved passage | What the reader is shown about the sources |
| **Is it readable?** | Is it in plain English, at the level the question was asked in | Whether a revision pass runs |

These are independent. A correct refusal is fully *answered* and not *grounded*
at all. A fluent answer that quietly ignores half the question can be perfectly
grounded in the half it did address. An answer can be complete, well-sourced,
and written so densely that the person reading it cannot act on it. Collapsing
them into one number would hide all three failures.

### Plain English is a requirement, not a style preference

Answers default to **basic English**: short sentences, common words, the
structure a colleague would use out loud. This is not simplification of the
content — it is simplification of the language carrying it.

The distinction matters enough to state flatly: **plain English does not mean
fewer facts.** Every dose, every unit, every qualifier, every contraindication
and every caveat stays exactly as it was. What changes is the sentence around
them. "Administer prophylaxis in accordance with the weight-band schedule" and
"Give the dose for the child's weight band" carry identical clinical content;
only one of them can be read at speed by someone with a patient in front of
them. If simplifying a sentence would drop a qualifier, the sentence does not
get simplified — the qualifier wins.

Two things override the default:

- **The question's own register.** A health worker who writes in full clinical
  terminology gets an answer in the same terminology. Explaining `TDF/3TC/DTG`
  to someone who just typed it is condescending and wastes their time.
- **Terms with no plain equivalent.** A drug name, a regimen code, a scored
  clinical scale — these are named things. They are used, and briefly expanded
  the first time they appear, not replaced with an approximation.

This applies to the English answer. Under the translate-then-answer design the
Luganda reader receives a translation of it, so plain English upstream is also
what makes the Luganda output tractable: a short, concrete English sentence
survives machine translation far better than a long subordinate-clause one, and
the failure mode of translating dense clinical prose is exactly the kind of
mangled qualifier that matters most here.

### The revision back-flow

```text
  answer + question + cited passages
        |
        v
  review()                             one structured call, configured model
        |
        +-- both scores >= REVIEW_FLOOR -> done, nothing else runs
        |
        '-- either <  REVIEW_FLOOR      -> ONE revision pass
                |
                v
        revise(answer, gaps, passages)
          "here is your answer, here is what it did not cover,
           here are the passages. Fill the gaps. Change nothing else."
                |
                v
          revised answer -> re-reviewed once for grounding, then finalised
```

Four rules keep this from becoming a loop:

1. **It edits, it does not regenerate.** The instruction names the gaps and
   supplies the existing text. A regeneration would throw away a good paragraph
   to fix a missing one, and would produce a different answer each time the
   review was borderline.
2. **Exactly one pass.** If the revision still falls short, the answer is
   delivered as it stands. An answer that arrives is worth more than a better
   one that does not, and an unbounded loop is a way to spend a health worker's
   time without telling them.
3. **The revision may not add uncited clinical content.** It fills gaps *from
   the passages already retrieved*. If the gap cannot be filled from an approved
   source, the honest revision is to say the source does not cover it — which is
   the same rule the first answer was written under.
4. **Refusals are never revised.** An answer that correctly refused for lack of
   an approved source has done its job. Sending it back for "improvement" is how
   a refusal turns into a guess.
5. **Simplifying may not cost a fact.** A revision that rewrites for readability
   keeps every dose, unit, qualifier and contraindication intact. If a sentence
   cannot be made plainer without losing one, it stays as it is. Losing a
   qualifier is a clinical error; a long sentence is an inconvenience.

`REVIEW_FLOOR` starts at **0.4**, deliberately low. The revision pass is an
intervention, not a polish step: it should fire when an answer genuinely missed
what was asked, not whenever it could have been a little better. A high floor
would make almost every answer pay for a second model call, which is latency a
health worker feels and cost the deployment pays, in exchange for rewriting
answers that were already fine. Set low, the check stays what it is meant to be
— a floor under the bad cases rather than a gate every answer squeezes through.

Like the retrieval score floor, it is a number chosen to be adjusted from
measurement rather than defended as correct. The review outcome is recorded on
every answer, so the distribution can be read before the threshold is moved.

The review runs on the **English** text, before translation — the same rule the
whole pipeline follows, and for the same reason: the model reasons in the
language the corpus is in.

---

## Citations and grounding

A cited passage is stored, not recomputed. When an answer completes:

1. Citation markers are extracted from the **finished** English answer. Not per
   token — providers split `[12]` across three tokens, so per-token matching
   finds nothing.
2. Marker `N` maps to the `N`-th passage placed in the prompt. A marker beyond
   the passages supplied is dropped with a warning rather than trusted.
3. Only the passages the answer **actually cited** are persisted, with their
   text, scores, source id and version. Storing the rest would show a reader
   sources the answer never leaned on.
4. The message and its citations commit in one transaction, so citations survive
   a reload rather than living only in the stream.

In the UI, each `[n]` is a link that opens the passage it points at. A reader can
also ask for a plain-language gloss of one passage, generated on demand and
cached. The gloss never replaces the passage, the model generating it sees only
the passage — not the question, not the history — and a failure shows no gloss
rather than a guess.

Version is part of a citation's identity. Two editions of one guideline are
different sources clinically, and a reader must be able to tell which was used.

### Showing how well an answer is grounded

Today an answer that cites nothing and an answer built out of the Uganda
Clinical Guidelines look identical on screen. A health worker cannot tell which
one they are reading, and that is the difference that matters most to them.

**A weakly grounded answer is still shown.** It is not suppressed, not
regenerated, and not marked as an error. Withholding a useful answer because the
library is thin would be a worse failure than showing it plainly. What changes
is the *reference display*, which tells the reader how much of what they just
read rests on an approved source.

Grounding is computed deterministically from data already in hand — no extra
model call:

- **Citation coverage.** Of the answer's substantive sentences, how many carry a
  citation marker. This is the headline signal.
- **Lexical grounding.** How much of the answer's clinical content — drug names,
  doses, numbers — actually appears in the cited passages. `tokenize()` in
  `heal/knowledge/embedder.py` already extracts exactly those tokens, keeping
  `TDF/3TC/DTG` and `500mg` intact. This is the supporting signal, and it is
  what catches an answer that cites a passage but states something the passage
  does not contain.

Three states, and the reference panel renders each differently:

| State | What it means | How it reads |
| --- | --- | --- |
| **Grounded** | Most substantive statements cite an approved source | The reference list, as normal |
| **Partly referenced** | An approved source was used, but much of the answer goes beyond it | The references shown, with it stated plainly that parts of the answer are not covered by them |
| **General knowledge** | No retrieval ran, by design — a general health question routed not to retrieve | Labelled as general information, with no reference list to imply otherwise |

Two things this must not do:

- **It must not present a refusal as a failure.** An answer that correctly
  declines for lack of an approved source is completely honest and zero percent
  grounded. `AgentResponse.refused_unsourced` already distinguishes it, and it
  is shown as what it is.
- **It must not invent precision.** "78% grounded" implies a measurement that
  has not been made. Plain counts — *"3 of 4 statements cite an approved
  source"* — say the same thing without the false decimal point. This choice
  changes what gets computed, which is why it is settled here rather than in the
  UI.

For a Luganda session the score is computed on the **English** text before
translation, because that is the text the citations were extracted from.

---

## Feedback

Feedback is the only signal that says whether any of this works in the field, so
it is collected on the answer itself rather than buried in an admin export.

**A five-star rating, not a thumbs pair.** Thumbs up/down forces a binary
judgement on a thing that is rarely binary: an answer can be correct but
incomplete, or well-sourced but hard to act on. Five points give a health worker
somewhere to put "useful but not quite", which is the most common real reaction
and the one a binary control throws away. An optional comment stays available
for the cases where the number is not enough.

Ratings aggregate per source and per answer through a **sigmoid**, so that the
first few ratings move the score meaningfully and later ones move it less. A
linear average lets a single early rating dominate, and lets a popular source
accumulate an unbounded score; a bounded curve does neither.

**What the aggregate is allowed to do — and what it is not.** It is a *review
signal*: it surfaces in the admin screens as "these are the answers and sources
health workers rate poorly", and that is what drives a human to look at the
underlying guideline. It is deliberately **not** wired back into the retrieval
score.

That is a change from the inherited system, which fed document feedback through
a sigmoid into a 0.5×–2.0× multiplier on the retrieval score. The mechanism was
reasonable for ranking web-like documents by popularity. For clinical guidance
it means a source can be quietly demoted below the evidence threshold because
users disliked answers built from it — with no audit trail, and no clinician in
the loop. If reweighting is ever needed here it will be admin-set, versioned,
recorded against a named actor, and visible. The curve is kept; the automatic
authority over what a health worker gets told is not.

---

## Ingest

One job, triggered by a person, running in a thread on the API process.

```text
  reference_ingest(source_file, actor)          heal/knowledge/
    validate upload
    extract text
    chunk                    1200 chars, 200 overlap
    for each batch of 32:
        embed                gte-small, in-process
        write Qdrant points  ALWAYS UNAPPROVED
        report progress      (phase, done, total)
    write PostgreSQL source + version + chunk rows
    apply approval           as a separate final step
```

Three properties are deliberate:

- **Chunks are always written unapproved,** and approval is applied at the very
  end even when "approve immediately" is ticked. Batches land one at a time, so
  a document is briefly incomplete; writing it pre-approved would let retrieval
  cite half a guideline.
- **A crash costs one batch, not the document.** Point ids derive from
  `(source_id, version, ordinal)`, so re-uploading the same title and version
  repairs a partial document rather than duplicating it.
- **Job state lives in memory on purpose.** A restart kills the embedding
  thread, so a database row reading "embedding, 412/1242" would outlive the
  thing it describes. The job endpoint reports that the upload needs retrying.

Embedding and extraction run in a thread pool, not on the event loop. Before
that, one upload froze the whole API — `/health` itself timed out.

PostgreSQL commits first and Qdrant is written after, because Postgres is the
system of record and the index is reconstructible from it. Two stores can still
drift; the answer is an admin-triggered reconcile that compares chunk rows
against point ids and **reports** the difference rather than repairing it
silently.

---

## Schema and migrations

PostgreSQL is the system of record. `api_server` runs `alembic upgrade head` on
start, which is a no-op against a database already at head.

The history is **the inherited 49-file chain with Heal's migrations appended** —
currently `a1c4f7d2e9b0` (three-tier roles). It was not squashed into a new
baseline, so the schema still contains the retired tables: connectors, document
sets, Slack configuration, user groups, tags. They are empty and cost nothing,
but a fresh reader will find tables no code reads.

**If a new baseline is ever written, one rule governs it: production is
stamped, never upgraded.** `alembic stamp` writes the revision id and executes
no DDL. Running a baseline as an upgrade against a database that already has
those tables will attempt `CREATE TABLE` on existing tables and fail — or
partially apply. The acceptance gate for such a change is a clean
`pg_dump --schema-only` diff between production and a freshly migrated
database, and it needs a verified backup before it starts.

Dropping the retired tables is a separate forward migration, on evidence that
nothing reads them.

### Identifiers

**Anything a user can hold a URL to gets a UUID, not a sequential integer.**
Chat sessions and chat messages are the ones that matter today.

The inherited schema numbers them `1, 2, 3…`, which has three problems in a
health product:

1. **They are guessable.** `/chat?chatId=41` invites `/chat?chatId=42`. The
   access check is what actually stops that — every session load verifies
   ownership — but an identifier that makes the attempt obvious is a weak place
   to be one bug away from a clinical conversation belonging to someone else.
2. **They leak volume.** A sequential id tells anyone who sees one roughly how
   many conversations the system has ever had, and two ids taken a week apart
   tell them the rate. That is business information given away for free.
3. **They assume one writer.** Sequences are per-database. A UUID can be
   generated anywhere — including in a client or a worker — without
   coordination, which is what keeps an export, an import or a second instance
   from colliding.

The cost is real and worth stating: UUIDs are wider than integers, index less
compactly, and do not sort chronologically. At Heal's scale none of that is
material — this is thousands of rows, not billions — and `created_at` already
carries the ordering that a sequential id was implicitly providing.

The internal, non-addressable tables keep their integer keys. This is about
identifiers that travel in URLs and API payloads, not about a schema-wide
conversion for its own sake.

---

## What used to run in the background

Worth recording, because removing it is the largest single simplification and
the reasoning should outlive the memory of it.

The `background` service was a **second full copy of the backend image** running
`supervisord`, which started five long-lived programs: a document-indexing loop,
a Celery worker, Celery Beat, a Slack listener, and a log tailer.

| Observation | Consequence |
| --- | --- |
| Beat polled for document-set sync **every 5 seconds** | ~17,000 database round trips a day, every one finding nothing. |
| The indexing loop ran **every 10 seconds, forever** | ~8,600 iterations a day polling connectors that were never configured. |
| Dask spawned N workers, each loading torch and the embedding model | Usually the largest resident-memory line in the deployment — larger than Vespa. |
| The container carried the LLM API key | Key mounted into a service that did not need it. |
| The Slack listener failed five starts, then stayed dead | Log noise, zero function. |
| Supervisor + Celery + Beat + Dask | Four process supervisors, four failure modes, four log formats — including a documented workaround for a Celery/SQLAlchemy segfault. |

All five existed to feed Vespa from external connectors. None of it served a
health worker asking a question.

**What replaced it: nothing.** A request comes in, an answer streams out, rows
are written. Ingest is the one job, and a person triggers it.

---

## Advantages

**The whole product runs on one machine.** Five containers, one command, no
GPU, no cluster, no cloud dependency beyond the LLM API. The embedding model is
64 MB and lives in the image; the vector index for the target corpus is a few
megabytes.

**That makes development and testing genuinely parallel.** Every developer,
tester or clinical reviewer runs the entire system on their own laptop —
including retrieval, ingest and the admin screens — rather than queueing for a
shared staging environment. Two people can test conflicting changes at the same
time on different machines, each with their own database and their own document
library, and neither can break the other's run. For a small team shipping
iteratively, this is worth more than any single technical optimisation in this
document: the cost of trying something is a rebuild, not a deployment.

**Small surface, few failure modes.** Removing the worker fleet removed four
process supervisors, a message broker, a scheduler, a distributed compute
cluster and a search engine. What remains can be held in one person's head,
which matters more than elegance when something breaks during a pilot.

**Decisions are auditable.** One classification call, one recorded route, one
versioned safety instruction, one audit event per answer. When an answer is
wrong, it is possible to say *why* it was wrong — which model, which route,
which sources, which safety version.

**Retrieval failure is a sentence, not an outage.** Every failure path in the
retrieval and translation stack degrades to something a health worker can act
on.

**The expensive decisions are reversible.** Vector store, chat model,
translation provider and route table each sit behind a seam. Swapping any of
them is a contained change rather than a rewrite.

**Cost scales with use, not with idle time.** The old stack burned CPU and
memory continuously whether or not anyone asked a question. This one is idle
when nobody is using it.

---

## Limitations and risks

Stated plainly, because the system is going to a small public and the people
running it need to know where it is thin.

### Not yet measured

- **The score floor is a guess.** `MIN_RETRIEVAL_SCORE = 0.35` is a placeholder.
  Until it is set from measured data, the boundary between "cites a source" and
  "refuses" is unvalidated — in both directions.
- **There is no clinician evaluation set.** Recall, citation correctness,
  emergency routing and unsafe-answer rates are all unmeasured on Heal's own
  corpus and question distribution. This is the single largest gap.
- **Lexical retrieval is untested on real drug codes.** The sparse-vector
  implementation exists specifically to handle `TDF/3TC/DTG` and `500mg BD`, but
  no evaluation case has yet confirmed it does.
- **Translation quality is on the clinical path and has no test set.** A
  mistranslated negation or dosage unit is a clinical error that no amount of
  retrieval quality will catch.

### Structural

- **Single instance of everything.** One Postgres, one Qdrant, one API process.
  No replicas, no failover. Acceptable for a small pilot; not for more.
- **Ingest competes with chat for CPU.** Embedding runs in a thread pool on the
  API process. A large document indexes without freezing the API, but it does
  consume the same machine.
- **Ingest progress does not survive a restart.** Deliberate — see *Ingest* —
  but it means an interrupted upload must be retried, and the operator has to
  understand why.
- **Drift between PostgreSQL and Qdrant is possible.** There is no continuous
  reconciliation, only an admin-triggered report. Silent divergence would show
  up as a source that is approved but never cited.
- **No reranker and no corpus-statistics BM25.** The ranking stack is
  deliberately simpler than what it replaced, and for a larger or noisier corpus
  that simplicity would start to cost recall.
- **Dependency on an external LLM provider** for both answers and intent
  classification: availability, latency, cost and data handling are all outside
  this system's control.
- **The migration history is still the inherited one.** All 49 original
  migrations remain, with Heal's appended. The retired tables — connectors,
  document sets, Slack config, user groups — still exist in the schema, empty.
  They cost nothing to keep, but a fresh reader of the database will find tables
  that no code reads.
- **`deprecated/` is still in the tree.** Frozen, unimported and gated in CI,
  but present. Deletion is a separate change once the pilot is stable.

### Operational

- **Qdrant has no authentication by default.** A store on the private compose
  network is acceptable and warns loudly; anywhere reachable over a network, an
  API key is required and refused if missing.
- **The emergency contact number is a configuration default** (`912`). It must
  be set deliberately per deployment.
- **Admins currently hold super-admin powers.** `PRIVILEGED_ROLE` is set to
  `ADMIN`; tightening it to `SUPER_ADMIN` is one line, and a test asserts the
  current state so the change has to be deliberate.
- **The web image is slow to build** (~25 minutes; the Next.js compile is the
  long pole). Budget for it.

---

## Capacity

| Target | Approach |
| --- | --- |
| ~100 approved documents, a few thousand chunks | One Qdrant node, one PostgreSQL node, in-process embedding. Roughly 2,000 × 384 × 4 bytes ≈ 3 MiB of raw vectors. |
| ~700 registered users | Same topology; rate-limit and monitor usage. |
| 20–50 simultaneous chats | Multiple stateless API workers, connection pooling, streaming limits, and an LLM rate-limit budget. Needs load testing. |
| 700 simultaneous chats | A separate exercise: scale API workers horizontally, move ingest to its own queue, size provider limits, measure p95, add Qdrant replicas only if search latency actually requires it. |

The first bottlenecks will be LLM latency and provider rate limits, streaming
worker capacity, and database connections — not vector search over a few
thousand chunks. Retrieval quality comes from approved sources, chunk
boundaries, translation quality and the evaluation set, not from a bigger
database.

---

## Reference material

- [OpenAI API reference](https://platform.openai.com/docs/api-reference)
- [Qdrant installation](https://qdrant.tech/documentation/installation/)
- [Qdrant security](https://qdrant.tech/documentation/security/)
- [Qdrant hybrid search](https://qdrant.tech/documentation/concepts/hybrid-queries/)
- [`thenlper/gte-small` model card](https://huggingface.co/thenlper/gte-small)
- [`BAAI/bge-m3` model card](https://huggingface.co/BAAI/bge-m3) — the
  multilingual option, and why it is not used
- [Onyx (successor to Danswer)](https://github.com/onyx-dot-app/onyx)
