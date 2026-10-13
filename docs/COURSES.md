# Course workspaces

Create a course, then add a PDF, PPTX, audio/video recording, or browser/microphone recording. Existing recordings are registered under **Imported lectures** without changing their IDs, files, transcripts, or saved packs. Empty installations start with no courses.

Document uploads extract and save content first. Once extraction is ready, choose **Generate study pack**. Recording uploads retain their automatic transcription and generation workflow. Study packs belong to one source; unified course packs, retrieval/chat, and mastery dashboards are deferred.

## Setup

Install `backend/requirements-dev.txt` into `.venv`, and run `npm ci` in `frontend`. Copy `.env.example` to `.env` and configure:

```dotenv
MODEL_PROVIDER=cerebras
CEREBRAS_BASE_URL=https://api.cerebras.ai/v1
CEREBRAS_API_KEY=your-server-side-key
CEREBRAS_TEXT_MODEL=qwen-3.8-27b
CEREBRAS_VISION_MODEL=qwen-3.8-27b
LIBREOFFICE_PATH=soffice
MAX_DOCUMENT_PAGES=500
```

For another OpenAI-compatible cloud provider, change `CEREBRAS_BASE_URL`, the API key, and model names. See [provider configuration](FOUNDATION.md#provider-configuration) for compatibility requirements and the token-limit field setting. Your account must have access to the configured vision model and image inputs. No credentials are embedded in the browser or committed to Git.

Install LibreOffice separately for PPTX rendering. On macOS an application install usually exposes `/Applications/LibreOffice.app/Contents/MacOS/soffice`; on Windows use `C:/Program Files/LibreOffice/program/soffice.exe`. Set `LIBREOFFICE_PATH` accordingly. Missing LibreOffice fails only slide ingestion, with a readiness instruction. PDF extraction/rendering uses bundled PDFium through `pypdfium2` and does not require Poppler or Tesseract.

For existing offline text workflows, set `MODEL_PROVIDER=lm_studio` and configure the existing LM Studio variables. The Settings default remains local for compatibility; the example environment selects Cerebras. Scans and visual documents require cloud mode and a vision-capable model; there is no silent cloud fallback. Recording transcription always uses the existing local Whisper/FFmpeg configuration.

## Ingestion and evidence

- Preserve original uploads under the configured data directory. The upload limit remains 200 MB; documents are additionally limited to 500 pages/slides by default. PDF and PPTX are supported; legacy `.ppt` is not.
- Extract native text and render page images once. PPTX is converted to PDF in a separate LibreOffice profile per source, with a 120-second conversion timeout; rendered page count must match slide count.
- Select vision when native text has fewer than 80 characters after trimming, image coverage reaches 15%, or local signals indicate charts/tables/diagrams (including substantial vector drawing). This is a heuristic, not perfect visual-content detection. Pages with ordinary text do not automatically incur vision calls.
- Send one selected image per vision request, using a single document worker. Cache results by source version, image bytes, provider base URL, vision model, and prompt. Source files are immutable; replacing a file means uploading a new source.
- Keep native text and vision output separately. Flag uncertain content and exclude it from confident generated evidence. Failed sources retain completed extraction so users can inspect it, retry extraction, or generate from available reliable units.
- Persist stable UUID content-unit IDs before requesting a study pack. The model cites these IDs; the backend checks them against the evidence supplied and resolves them to source/location metadata. Invalid citations receive one repair attempt and then fail generation. This validates citation provenance, not semantic truth of every claim.
- Legacy lecture APIs keep segment-based citations through a compatibility translation. Course source APIs expose `content_unit_ids`.

Documents progress through `queued → extracting → indexing → ready`, with explicit `generating`, `failed`, and `cancelled` states. Indexing currently persists addressable evidence; it does not build a semantic retrieval index. Retry extraction reuses completed rendering/vision. Restart resumes interrupted extraction or generation. Cancellation retains originals and completed results; deleting a source removes its files and evidence. A course must be empty before deletion.

Cloud mode sends generation text and selected page images to Cerebras. Course management works without provider credentials. Model-run records contain provider/model, feature, prompt version, latency, usage when available, and transport outcome; they contain no prompts, source text, or API keys. Local-provider usage counts are unavailable in the current adapter.

## API

All paths have the `/api` prefix.

| Methods | Path | Behavior |
|---|---|---|
| GET, POST | `/courses` | List/create courses |
| GET, PATCH, DELETE | `/courses/{id}` | Read/edit/delete empty course |
| GET, POST | `/courses/{id}/sources` | List source summaries / multipart upload (`file`, optional `title`) |
| GET, DELETE | `/sources/{id}` | Source detail including content units and pack / permanent deletion |
| GET | `/sources/{id}/status` | Persisted status, progress, error |
| POST | `/sources/{id}/retry`, `/cancel`, `/generate` | Retry extraction, cancel, generate source pack |
| GET | `/sources/{id}/asset` | Original PDF/recording or rendered PPTX PDF |
| GET | `/sources/{id}/units/{unit_id}/image` | Image constrained to that source |
| GET | `/citations/{unit_id}` | Source/course IDs, excerpt, uncertainty, page/slide/timestamp location |
| GET | `/sources/{id}/export.md` | Source pack with resolved evidence links |

Course create/edit bodies contain `title` (1–200 characters, trimmed) and `description` (up to 5,000 characters). Source detail returns content units with IDs, backend-derived locations, native/combined text, uncertainty, and preview URLs; internal filesystem paths are omitted. New study-pack items cite `content_unit_ids`. Backend resolution supplies `page_no`, `slide_no`, or `start_sec`/`end_sec` through the citation endpoint.

The existing `/lectures` APIs remain available. Uploads accept an optional `course_id` form field; `/lectures/demo` accepts a `course_id` query parameter. Unassigned legacy uploads enter Imported lectures. This remains a single-user localhost application; source grouping is not multi-user authorization.

## Verification

```bash
.venv/bin/python -m pytest
cd frontend
npm test
npm run build
```

Tests cover data-preserving migration, course isolation, native PDF extraction, selective vision/cache reuse, content-unit citation validation/resolution, extraction failures, generation recovery, cancellation during native processing, gateway retries, and frontend course routes/citation navigation. Live Cerebras calls and a real LibreOffice conversion require configured external tools and credentials.
