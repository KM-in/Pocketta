# Multi-source course knowledge and study packs

PocketTA keeps two searchable representations of original course material:

1. **Passages:** reliable page, slide, and timestamp units split at paragraph/word boundaries. Defaults are 1,200 characters with 160-character overlap; offsets and original locations are preserved.
2. **Routing summaries:** section summaries from batches of at most 8,000 evidence characters, plus a source overview reduced through bounded summary batches. These contain topic labels and links to original chunk IDs. Generated study packs are not added to either search index.

New extraction jobs build both layers automatically using the selected generation model. Missing models, failed summaries, or failed embeddings leave extracted material and keyword passage search usable. Source details and cards expose passage, summary, and embedding readiness. Existing material gets its first summaries through **Rebuild selected indexes** or a course-pack job, not a billed startup backfill. Interrupted summary work resumes; existing summaries can have vectors rebuilt without generating their text again.

## Configuration

Install the updated backend requirements (including NumPy), then configure the ignored `.env` file and restart the backend:

```dotenv
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=your-embedding-service-key
EMBEDDING_MODEL=text-embedding-3-small
RETRIEVAL_CHUNK_CHARS=1200
RETRIEVAL_CHUNK_OVERLAP_CHARS=160
RETRIEVAL_CONTEXT_CHARS=24000
CEREBRAS_REASONING_EFFORT=medium
```

Omitting `EMBEDDING_API_KEY` or `EMBEDDING_MODEL` uses the existing `OPENAI_API_KEY` or `OPENAI_EMBEDDING_MODEL`. An explicitly empty key is supported for loopback embedding servers. For a local OpenAI-compatible service, set `EMBEDDING_BASE_URL=http://127.0.0.1:1234/v1`, `EMBEDDING_API_KEY=`, and your loaded embedding model. Cloud endpoints require a key. Embeddings use `/embeddings`, independently of the text/vision provider.

Endpoint and model identities are stored with vectors; dimension mismatches are never compared. Changing embedding configuration rebuilds vectors when indexing runs. Changing source content, chunk settings, summary model/endpoint, reasoning effort, or the summary prompt invalidates affected summary caches. Process environment variables take precedence over `.env`.

Generation still uses medium reasoning by default and 72,000 output tokens. Retrieval context is separately bounded to 24,000 evidence characters per model call.

## Search and tutor

Select source checkboxes to narrow search; no selection searches the full current course. Both layers use keyword and optional semantic ranking. Summary matches expand their original supporting passages while direct passage search covers all selected sources. Reciprocal-rank fusion, source diversity, and overlapping-window suppression select the final evidence. Default six results, maximum twelve.

Search responses and tutor prompts contain original excerpts with page, slide, or timestamp citations. Summaries only route retrieval; they never become authoritative evidence. The existing tutor continues to verify answers separately. When semantic search is unavailable, the interface reports the keyword fallback.

## Course packs

Select sources and click **Generate course study pack**. The queued job indexes sources inline in its existing course scheduler slot, builds up to twelve topics, and generates sections in batches of at most eight sources and twelve passages. Notes, concepts, and flashcards cite original chunk IDs and are independently verified. After all sections are assembled, one mixed quiz is generated across the selected sources and added to the quiz library. A quiz failure leaves the completed pack available for a separate retry. Conflicting or unsupported synthesis becomes a visible coverage gap.

Validated topic batches are saved before assembly. Identical items are removed, the overview is verified against original excerpts, and the source-coverage panel identifies cited and omitted sources. Packs can be cancelled or retried. Retry reuses validated sections while source fingerprints remain unchanged. Interrupted jobs resume after restart. Edits or deletion mark affected packs stale; generate a new pack against current sources.

Multiple file uploads use at most two simultaneous transfers. A failed upload does not remove successful uploads. Source-level study packs remain available.

## APIs

| Method | Route | Input / response |
|---|---|---|
| POST | `/api/courses/{course_id}/retrieve` | `query`, optional `limit` and `source_ids`; original evidence plus layer diagnostics |
| POST | `/api/courses/{course_id}/index` | Required `source_ids`; queued layer status for each selected source |
| GET | `/api/sources/{source_id}/knowledge` | Passage, summary, and embedding status/counts |
| POST | `/api/courses/{course_id}/study-packs` | Required `source_ids`; HTTP 202 queued pack |
| GET | `/api/courses/{course_id}/study-packs` | Saved course packs |
| GET | `/api/courses/{course_id}/study-packs/{pack_id}` | Topics, overview citations, progress, snapshots, warnings, and coverage |
| POST | `/api/courses/{course_id}/study-packs/{pack_id}/cancel` | Cancel queued or active work |
| POST | `/api/courses/{course_id}/study-packs/{pack_id}/retry` | Resume a failed/cancelled pack with unchanged evidence |

All source selections are validated against course membership. Summary tables, evidence links, pack jobs, and section progress use additive, idempotent SQLite migrations.

## Adaptive quizzes and syllabus

The course workspace includes a quiz library, a custom quiz form, learning progress, and an optional Markdown syllabus. Custom quizzes accept selected sources, question count and mix, difficulty, included/excluded topics, and free-text instructions. Topics from an active syllabus or the searchable source summaries seed the topic list. Questions are verified against cited original passages; source snapshots and the learning profile are stored with each immutable quiz.

Attempts autosave answers and can be resumed. Multiple-choice items are scored deterministically; short answers use the configured grader. Answer keys and explanations are revealed when a graded attempt is reviewed. Retakes create new attempts. Confident observations update topic history; uncertain grades stay visible but do not count toward mastery. Topic estimates use Bayesian Knowledge Tracing (BKT), replaying reliable graded observations in time order with `P(L0)=0.20`, `P(learn)=0.15`, `P(guess)=0.20`, and `P(slip)=0.10`; scores of at least 0.70 count as correct. These are transparent MVP assumptions, not fitted parameters. The UI says “insufficient evidence” until three reliable observations exist. A topic is marked mastered only with at least three distinct questions across two quiz/check sessions and a BKT posterior of at least 0.80. Tutor understanding checks contribute observations; ordinary tutor messages do not. Each topic retains observation count, recent mistakes, and last-practised time for adaptation.

Numerical questions use a stored finite answer, non-negative absolute tolerance, and optional unit. Submission grading parses a finite numeric answer and checks both tolerance and unit on the server. Question records include type, topic, difficulty, cited chunks, and an immutable version; only questions that pass the separate verifier are saved. Generation is rejected when a prompt exactly matches or has at least 0.88 token-set Jaccard similarity to an existing course question. Tutor explanations receive topic-level learning guidance from retrieved topic tags, but ordinary chat does not write learner observations.

SQLite is authoritative for attempts and learning observations. After grading, the app atomically regenerates `courses/{course_id}/user_learning.md` under `POCKETTA_DATA_DIR`. Downloading the report also regenerates it if missing. The optional syllabus is stored in SQLite and mirrored to `courses/{course_id}/syllabus.md`. The UI extracts headings and list items as proposed topics, suggests source mappings with passage links, and waits for confirmation before activating the syllabus. Material availability, studied status, assessment, and mastery stay separate; adding a source does not mark it studied.

| Method | Route | Purpose |
|---|---|---|
| GET / POST | `/api/courses/{course_id}/quizzes` | List or generate a custom quiz |
| GET / POST | `/api/courses/{course_id}/quizzes/{quiz_id}` | Retrieve a quiz; answers appear after a completed attempt |
| POST | `/api/courses/{course_id}/quizzes/{quiz_id}/attempts` | Start a new attempt |
| GET / PUT | `/api/courses/{course_id}/quiz-attempts/{attempt_id}` | Resume the attempt or save answers through `/answers` |
| POST | `/api/courses/{course_id}/quiz-attempts/{attempt_id}/submit` | Grade saved answers; retry continues unfinished grading |
| GET | `/api/courses/{course_id}/learning` | Topic observations and four syllabus progress dimensions |
| GET | `/api/courses/{course_id}/learning/user_learning.md` | Regenerate and download the learning report |
| GET / PUT | `/api/courses/{course_id}/syllabus` | Read or propose syllabus topics from Markdown |
| POST | `/api/courses/{course_id}/syllabus/confirm` | Confirm corrected topic-to-source mappings |
| PATCH | `/api/courses/{course_id}/syllabus/topics/{topic_id}/studied` | Mark a topic studied or clear that marker |
| POST | `/api/courses/{course_id}/study-packs/{pack_id}/quiz/retry` | Retry a failed pack quiz |
| POST | `/api/courses/{course_id}/study-packs/{pack_id}/import-quizzes` | Import historical pack quiz items into the library |

## Privacy, cost, and validation

With cloud models, automatic summaries send reliable source excerpts to the generation provider; embedding calls send source chunks, summaries, and search queries to the embedding provider. Provider usage and verification outcomes are recorded without prompts or credentials. Cached summary text and validated sections avoid repeated generation where possible.

Tests isolate local `.env` and process credentials and use synthetic excerpts plus mocked providers. Run `python -m pytest`, then `npm test` and `npm run build` in `frontend`. The multi-source fixture contains paraphrases and a disputed busy-waiting claim. Mocked verification proves rejection handling, not a model's real-world faithfulness.

Run `python -m backend.app.tools.benchmark_retrieval` for the offline 10,000-chunk/1,536-dimension scoring benchmark. On Windows 11, Intel64 Family 6 Model 154, Python 3.14.7, the measured cold build was 3.86 seconds and warm p95 scoring plus top-40 ranking was 0.0056 seconds. This excludes SQL reads, network latency, and model generation; it is not an end-to-end search latency guarantee. The 50-source/10,000-chunk target is a benchmark scale, not a new upload cap.
