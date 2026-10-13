# Model and processing foundation

PocketTA runs as one FastAPI process with SQLite. Uploading a source queues document extraction or recording processing. The [knowledge base](KNOWLEDGE.md) now indexes extracted sources and uses the embedding interface for semantic retrieval. Rubric grading remains an internal capability for later saved assessments.

## Provider configuration

Keep all credentials in the server environment or an ignored `.env` file:

| Setting | Default | Purpose |
|---|---|---|
| `MODEL_PROVIDER` | `lm_studio` | Text provider: `lm_studio` or `cerebras` |
| `CEREBRAS_BASE_URL` | `https://api.cerebras.ai/v1` | OpenAI-compatible cloud API root for text and document vision |
| `CEREBRAS_API_KEY` | empty | Key for the configured cloud endpoint |
| `CEREBRAS_COMPLETION_TOKEN_FIELD` | `max_completion_tokens` | Token-limit field; also accepts `max_tokens` |
| `CEREBRAS_TEXT_MODEL`, `CEREBRAS_VISION_MODEL` | `qwen-3.8-27b` | Cloud model selection |
| `LM_STUDIO_MODEL_ID` | empty | Exact loaded local text model |
| `OPENAI_API_KEY` | empty | Independent key for embedding calls |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `VERIFIER_MODEL`, `GRADER_MODEL` | empty | Override text model on the selected text provider; empty uses the text model |
| `GENERATION_TIMEOUT_SECONDS` | `480` | Request timeout |
| `GENERATION_CHUNK_CHARS` | `14000` | Study-pack chunking threshold |
| `GENERATION_CHUNK_OVERLAP_SEGMENTS` | `1` | Study-pack chunk overlap |

Existing `LM_STUDIO_TIMEOUT_SECONDS`, `LM_STUDIO_CHUNK_CHARS`, and `LM_STUDIO_CHUNK_OVERLAP_SEGMENTS` remain supported. An explicitly set `GENERATION_*` value takes precedence over its legacy counterpart. Do not set both unless migrating configuration deliberately.

To use another cloud provider, keep `MODEL_PROVIDER=cerebras` (the existing cloud adapter name) and set `CEREBRAS_BASE_URL`, `CEREBRAS_API_KEY`, and the text/vision model IDs to that provider's values. Include the API version path in the base URL; PocketTA appends `/chat/completions` or `/models`. Trailing slashes are removed. Set `CEREBRAS_COMPLETION_TOKEN_FIELD=max_tokens` when required by the provider. Restart the backend after changing `.env`. The provider must support OpenAI-compatible chat completions and JSON-schema structured output; document vision additionally requires image inputs. Native APIs with different request/response formats need an adapter. Verifier and grader overrides use this same endpoint. Model-run records and token-rate keys retain the `cerebras` adapter name. OpenAI embeddings remain independently configured.

`/api/health` shows embedding configuration and effective verifier/grader models. These are configuration checks, not proof of cloud connectivity or model access. Missing OpenAI credentials do not affect readiness for existing source processing.

The configured cloud provider receives generation excerpts and selected page/slide images. Knowledge indexing sends reliable source chunks to OpenAI when configured, and semantic search sends query text, including in local text mode. Transcription and storage remain local. Browser keys and client-side provider requests are never needed.

## Internal interfaces

- `ModelGateway.generate(transcript, source_id=...)`: grounded study-pack generation with request-local source attribution.
- `generate_structured(prompt, schema, role="generation")`: Pydantic-validated output; role may be `generation`, `verification`, or `grading`.
- `embed(texts)`: ordered vectors, validated for input count, indices, dimensions, and finite numeric components. Empty batches return an empty list; blank inputs fail locally. Provider input limits apply; retrieval chunking/batch planning belongs to the next feature.
- `grade_answer(GradingInput)`: question, rubric, student response, and evidence → normalized score, confidence, feedback, uncertainty, and supporting content-unit IDs. Out-of-bundle IDs and invalid scores fail validation with one repair attempt. This does not persist attempts or change mastery.

Study-pack orchestration lives in `generation.py`; provider configuration and request coordination live in `providers.py`. The legacy `LMStudioService` remains a compatibility adapter, rather than a gateway parent.

## Scheduling and retries

| Setting | Default | Purpose |
|---|---|---|
| `JOB_CONCURRENCY` | `2` | Global concurrent document/recording jobs |
| `COURSE_JOB_CONCURRENCY` | `1` | Concurrent jobs in one course |
| `PROVIDER_CONCURRENCY` | `1` | In-flight requests per provider across all gateway instances |
| `PROVIDER_REQUEST_INTERVAL_SECONDS` | `0` | Minimum interval between request starts per provider |

The scheduler dispatches FIFO within each course and round-robin across eligible courses. Set `JOB_CONCURRENCY=1` on machines with limited RAM/VRAM. Provider requests share pacing and cooldowns independently of job limits. Network failures, 429s, and 5xx responses receive at most three attempts; exponential backoff starts at one second. `Retry-After` seconds or HTTP dates override that delay. Authentication and other non-transient HTTP failures do not retry.

Queued cancellation removes the job immediately. Active cancellation waits for cleanup, including document native work, before deletion. Server shutdown retains incomplete work for recovery; document extraction/generation intent and saved recording transcripts determine restart behavior.

Coordination is process-local. Run one Uvicorn worker; multiple processes would require a shared scheduler and rate-limit store.

## Usage and cost records

SQLite migrations preserve existing `model_runs` and add `course_id`, `attempts`, `validation_status`, `estimated_cost_usd`, and `cost_rates_json`. Each logical transport call records its attempt count, duration, usage, and completed/failed/cancelled outcome. Output validation is recorded separately so HTTP success does not imply a valid answer.

Provider-reported usage is preferred. Missing text usage uses a clearly marked character-based estimate (approximately four characters per token), not billing-grade tokenization. Missing image usage remains unknown. Costs remain null unless sufficient token counts and configured rates exist; local inference records zero external API cost. Prompt content, student responses, and credentials are not recorded in model-run metadata.

Configure `MODEL_TOKEN_RATES` as a JSON mapping from `provider/model` to USD per million input/output tokens. For embeddings only the input rate is required. Example shape, using placeholders rather than current prices:

```text
{"openai/YOUR_EMBEDDING_MODEL":{"input":YOUR_INPUT_RATE},"cerebras/YOUR_TEXT_MODEL":{"input":YOUR_INPUT_RATE,"output":YOUR_OUTPUT_RATE}}
```

Replace placeholders with numeric rates from your provider agreement. The rates used are stored with each estimate. An empty mapping is valid and keeps cloud estimates unknown.

## Validation and live smoke checks

Run `.venv/bin/python -m pytest`, then `npm test` and `npm run build` in `frontend`. Automated tests mock provider responses and native conversions; they do not prove real provider access.

With configured credentials and models, manually:

1. Upload a PDF and PPTX plus a recording across two courses. Confirm upload bytes progress, separate processing progress, cancellation, and queued restart recovery.
2. Generate a study pack using Cerebras, then LM Studio. Confirm citations still resolve to saved evidence locations.
3. In an async Python session, initialize `Database` and `CourseStore`, then call `ModelGateway.embed(["A process executes a program."])`. Confirm a vector and a validated OpenAI model-run record.
4. Call `generate_structured` with `role="verification"` and `grade_answer` with a known rubric/evidence example. Confirm selected model names, bounded grades, citations, and usage/cost metadata.
5. With real LibreOffice installed, confirm PPTX slide rendering and provenance. Do not claim this native integration is verified by mocked tests alone.
