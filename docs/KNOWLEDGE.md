# Shared course knowledge base

Every extracted PDF page, PPT/PPTX slide, timestamped transcript unit, and reliable analysed video-frame description is indexed as original evidence. Frame descriptions keep the sampled video timestamp and original frame image path, so citations seek the recording to that moment. Routing summaries form a second searchable layer; generated study packs are not indexed. The React course workspace offers source selection, **Search course material**, and multi-source course packs. See [two-layer indexing and course packs](MULTI_SOURCE.md) for configuration, API additions, and recovery behavior.

## Processing and provenance

Extraction/transcription now calls the knowledge service before marking processing complete. Older extracted sources are backfilled through the course scheduler at startup. Interrupted indexes resume on restart. Explicitly cancelled indexes stay cancelled until rebuilt.

Chunks remain within a single content unit, with overlapping word-boundary windows and exact character offsets. Each chunk retains its content-unit ID, source ID/version, original location, extraction confidence, and optional visual URL. Short transcript segments remain short rather than losing timestamp precision by merging unrelated units. Uncertain units and invalid locations are excluded.

SQLite stores chunks and vectors together; FTS5 indexes original chunk text. Semantic retrieval computes cosine similarity over current vectors in the requested course. This exact scan is intended for the small hackathon course, not a large multi-tenant corpus. No vector database or additional native dependency is required.

A complete index is published atomically after provider calls finish. Content edits, confidence/uncertainty changes, removed units, transcript corrections, source-version changes, and course reassignment invalidate old indexes. Transcript revisions increment source version. Retrieval checks source membership, current version, reliable content, and exact excerpt text, then checks again after an asynchronous embedding call. Deleted sources cascade to chunks, vectors, keyword rows, and chunk/topic links.

## Models and fallback

`EMBEDDING_PROVIDER=fastembed` is the default. It uses local CPU model `BAAI/bge-small-en-v1.5`, downloads weights once, and makes no paid embedding API calls. The `backend/requirements.txt` install includes FastEmbed; model weights are cached under `POCKETTA_DATA_DIR/fastembed`. An API key alone never switches providers. To deliberately opt into a billable OpenAI-compatible API, set `EMBEDDING_PROVIDER=api`; `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, and `EMBEDDING_MODEL` configure it, with `OPENAI_API_KEY` and `OPENAI_EMBEDDING_MODEL` as fallbacks. Changing embedding identity queues a rebuild at startup; vectors from different endpoints, models, or dimensions are never compared. Local embeddings use a separate configurable similarity threshold (`FASTEMBED_MIN_SIMILARITY`, default `0.80`) from API embeddings.

If credentials are absent or an embedding provider fails, original chunks and keyword search remain available as `keyword_ready`. The source extraction result remains usable. Index errors and search warnings disclose this fallback; rebuilding retries semantic indexing. Unknown provider costs remain unknown as described in [foundation configuration](FOUNDATION.md).

## Configuration

| Setting | Default | Purpose |
|---|---|---|
| `RETRIEVAL_CHUNK_CHARS` | `1200` | Maximum original-text characters per chunk, bounded to 200–6000 |
| `RETRIEVAL_CHUNK_OVERLAP_CHARS` | `160` | Overlap, smaller than chunk size |
| `EMBEDDING_BATCH_SIZE` | `32` | Inputs per embedding request |
| `RETRIEVAL_MIN_SIMILARITY` | `0.65` | Minimum cosine similarity for semantic candidates |
| `KNOWLEDGE_INFER_TOPICS` | `true` | Structured-model hierarchy, chunk tags, and inferred prerequisite links |

When enabled, model inference organizes excerpts into major topics, subtopics, and key concepts, tags chunks, and proposes prerequisites. Results are grounded in bounded excerpt batches; unknown chunk references and invalid hierarchy parents are rejected. Topic rows expose their `level` and `parent_topic_id`/`parent_name` through the topics API. If inference is disabled or unavailable, deterministic salient-term tags remain available. Inference sends source excerpts to the configured text provider and adds provider usage. Course/topic UUIDs derive from normalized names and survive reindexing. Prerequisite links are accepted only between topics in the same course, with confidence and `is_inferred=true`. Manually supplied links use `is_inferred=false` and are not overwritten by inference. Topic metadata is retained after source deletion so later learner history can keep stable topic identities; chunk links are removed.

## API and evidence contract

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/courses/{course_id}/retrieve` | `{query, limit?}` → bounded `EvidenceBundle` |
| GET | `/api/sources/{source_id}/knowledge` | Index status, error, model, fingerprint, chunk count |
| POST | `/api/courses/{course_id}/sources/{source_id}/index` | Queue a source rebuild; enforce course membership |
| GET / POST | `/api/courses/{course_id}/topics` | List topics/prerequisites or create a named topic |
| PUT | `/api/courses/{course_id}/topics/{topic_id}/prerequisites` | Save `{prerequisite_topic_id, confidence?}` as a manual link |

Example retrieval request:

```json
{"query":"How does round robin scheduling work?","limit":6}
```

Each evidence item contains `chunk_id`, `content_unit_id`, `source_id`, `source_name`, `source_version`, `excerpt`, rank `score`, `citation` (`page_no`, `slide_no`, or `start_sec`/`end_sec`), `char_start`, `char_end`, `confidence`, optional `visual_url`, and `topic_ids`.

Keyword candidates use escaped FTS terms and BM25 ranking. Semantic candidates use the configured cosine threshold. Reciprocal-rank fusion merges both lists, confidence weights ranks, and overlapping windows from one unit are suppressed. The default result limit is six, maximum twelve. No candidates yields `coverage="unsupported"`. `coverage="supported"` means candidate evidence exists; it does not certify support for every claim in a future generated answer. Claim-faithfulness validation belongs to section 3.

## Held-out fixture and checks

`backend/tests/fixtures/knowledge/os-course.json` contains synthetic textbook, slide, and lecture excerpts, six questions with known answers and exact locations, two unsupported questions, and intentionally uncertain evidence. It is reserved for retrieval checks and future tutor/assessment validation. It does not bundle real PDF/video assets or prove extraction quality.

Run:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m backend.app.tools.evaluate_retrieval
```

The evaluation uses a temporary database and keyword search by default. It reports per-query precision, recall, source-location hits, and unsupported results. Initial offline results: all six expected locations retrieved and both unsupported queries returned no evidence. Extra candidate excerpts reduce precision for some questions; this fixture is a smoke test, not a broad retrieval-quality benchmark.

Use `--live-embeddings` to run the synthetic fixture through the configured embedding provider; with the default local provider, model weights download on first use and are cached. Add `--output path.json` to save a report. The live FastEmbed smoke result is saved at [live-retrieval-fastembed-2026-10-14.json](evaluation/live-retrieval-fastembed-2026-10-14.json). It retrieves all six expected locations and rejects both unsupported queries on this fixture. This is a small synthetic check, not a broad retrieval-quality benchmark. Automated semantic tests use deterministic mocked vectors to verify paraphrase retrieval, model consistency, and isolation.
