# PocketTA

PocketTA organizes recordings, PDFs, and PPTX slides into course workspaces, extracts citable content, generates source-level study packs, and provides a cited course tutor. React, FastAPI, SQLite, and recording transcription run locally. Select an OpenAI-compatible cloud endpoint (Cerebras by default) for text and vision processing, or LM Studio for local text generation. The application binds to loopback addresses.

## What works

- Create and edit courses; collect recordings, PDFs, and PPTX slides within each course.
- Extract native document text, render previews, and selectively analyse scans or visual pages with Cerebras. Cache rendered pages and vision results across retries.
- Generate source-level study packs with validated content-unit IDs resolved to page, slide, or timestamp citations.
- Retry/cancel processing, restore interrupted work, and preserve existing recordings under an Imported lectures course.
- Show measured upload-transfer progress separately from processing progress.
- Schedule document and recording jobs fairly across courses, with shared provider concurrency and rate-limit cooldowns.
- Search original course evidence with hybrid keyword/embedding retrieval, exact page/slide/timestamp provenance, stable topics, and stored prerequisite links.
- Ask a course tutor for explanations, examples, comparisons, and explicit understanding checks; verify claim support separately from citation IDs.
- Restore course chat and saved check grades; open cited PDF pages/slides and seek recording timestamps.

See [Course tutor and citations](docs/TUTOR.md), [Course knowledge and retrieval](docs/KNOWLEDGE.md), [Model and processing configuration](docs/FOUNDATION.md) and [Course setup and API](docs/COURSES.md) for the new workflow and its boundaries.

The existing recording workflow also supports:

- Upload WAV, MP3, M4A, or MP4 recordings up to 200 MB.
- Normalize with FFmpeg and transcribe English locally with whisper.cpp.
- Mark low-confidence transcript segments and exclude them from confident generated evidence.
- Build notes, concepts, flashcards, and quizzes with Qwen 3.5 4B in LM Studio.
- Trace generated items to transcript segments, persist results, export Markdown, and permanently delete data.
- Record from a microphone or Chromium-based browser tab, cancel local work, correct transcript text, and retry generation without retranscribing.
- Show coarse persisted progress, stage timings, observed system-memory use, browser connectivity, and local runtime readiness.
- Start an attributed built-in demo and use the browser print dialog for PDF output.

This build omits unified course revision packs, verified assessment banks, adaptive assessments/mastery dashboards, diarisation, accounts, cloud sync, and native packaging.

## Prerequisites

- Python 3.11
- Node.js 22 or newer
- FFmpeg and FFprobe on `PATH`
- A locally built whisper.cpp CLI and `ggml-base.en.bin`
- Optional for NVIDIA GPUs: Faster Whisper, CUDA cuBLAS/cuDNN runtime libraries, and a prepared `turbo` model
- A Cerebras API key for cloud generation and document vision, or LM Studio with Qwen 3.5 4B for local text generation
- LibreOffice for PPTX rendering; PDF processing uses the Python dependencies

Normal app startup, health checks, and lecture processing never download a model. Prepare native tools and models while online, then use the local recording workflow without Wi-Fi.

## Clean project setup

Python dependencies live only in `.venv`; JavaScript dependencies live only in `frontend/node_modules`. System packages and LM Studio models are never removed.

macOS/Linux:

```bash
./scripts/bootstrap.sh --clean
```

Windows PowerShell:

```powershell
./scripts/bootstrap.ps1 -Clean
```

Copy `.env.example` to `.env`. For cloud mode, set `MODEL_PROVIDER=cerebras` and `CEREBRAS_API_KEY`. To use another OpenAI-compatible provider, set `CEREBRAS_BASE_URL` to its API root (including the version path) and configure `CEREBRAS_TEXT_MODEL` and `CEREBRAS_VISION_MODEL` with its model IDs. Set `CEREBRAS_COMPLETION_TOKEN_FIELD=max_tokens` if required; the default is `max_completion_tokens`. The endpoint must support JSON-schema structured output and, for document vision, image inputs. Restart the backend after changing configuration. Configure `LIBREOFFICE_PATH` for slides. For local text mode, set `MODEL_PROVIDER=lm_studio`. In LM Studio, load Qwen with a context length of at least 16K and start the local server on `127.0.0.1:1234`. Obtain the exact identifier from:

```bash
curl http://127.0.0.1:1234/v1/models
```

Set that value as `LM_STUDIO_MODEL_ID` in `.env`.

For embedding calls, separately set server-side `OPENAI_API_KEY`; `OPENAI_EMBEDDING_MODEL` defaults to `text-embedding-3-small`. Extracted source chunks are automatically embedded when OpenAI credentials are configured; otherwise keyword search remains available. `VERIFIER_MODEL` and `GRADER_MODEL` override the selected text model for those roles. Missing OpenAI credentials do not block existing processing. See [foundation setup](docs/FOUNDATION.md) for cost rates, scheduling, and smoke checks.

For NVIDIA CUDA transcription, install the optional Python dependency while online:

```bash
.venv/bin/python -m pip install -r backend/requirements-faster-whisper.txt
```

Install the NVIDIA CUDA libraries required by Faster Whisper for your OS, then prepare the default `turbo` model while online:

```bash
.venv/bin/python -m backend.app.tools.prepare_faster_whisper
```

Recording transcription remains local in either model mode. With `TRANSCRIPTION_BACKEND=auto`, PocketTA uses Faster Whisper when CUDA and the prepared model are ready, and otherwise falls back to whisper.cpp.

## Run

From the repository root, start the backend:

```bash
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, start the frontend:

```bash
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`. The readiness panel identifies any missing local prerequisite.

For YouTube or other tab audio, use a Chromium-based browser such as Chrome or Edge. Choose **Record browser tab audio**, select the browser tab in the share picker, and enable **Share tab audio**. Firefox and Safari do not currently expose compatible tab-audio capture for this workflow, so use file upload or microphone recording there.

PocketTA never starts, loads, or downloads models. Failed readiness rows include the local command or LM Studio action needed to fix them.

## Verify

```bash
.venv/bin/python -m pytest
cd frontend && npm test && npm run build
```

See [docs/README.md](docs/README.md) for native setup, cross-platform notes, and the offline acceptance checklist.

## Benchmark a prepared machine

For the historical local recording benchmark, with `MODEL_PROVIDER=lm_studio`, FastAPI, and LM Studio running:

```bash
mkdir -p benchmark-results
.venv/bin/python scripts/benchmark.py pocketta_test_10min.mp4 \
  --json-out benchmark-results/ten-minute.json \
  --markdown-out benchmark-results/ten-minute.md
```

The runner records observed stages and total time, then verifies evidence, uncertainty handling, summary presence, and demo item counts. Its output is ignored by Git.

The hardened 10-minute run on the 8 GB reference machine completed in 390.2 seconds: 1.0s normalization, 23.8s transcription, and approximately 365s structured generation. It produced 188 transcript segments, 14 notes, 6 concepts, 6 flashcards, and 5 quiz questions; every cited ID resolved and the one uncertain segment was not cited. This run used localhost services, but Wi-Fi-off status was not independently captured and is not claimed.

The bundled 2.5-minute demo completed a post-hardening local run in 88.4 seconds: 0.5s normalization, 6.1s transcription, and 81.7s generation. It produced 43 segments, 3 concepts, 5 flashcards, and 5 quiz questions with 21 distinct valid evidence citations. This run also used localhost services; it was not an independently recorded Wi-Fi-off run.

## Privacy and limitations

PocketTA binds to loopback addresses, restricts the LM Studio URL to loopback, ignores proxy environment variables for model calls, and contains no analytics, CDN assets, accounts, or model downloader. In Cerebras mode, source text used for generation and selected page/slide images leave the machine for cloud processing. Course indexing sends reliable source chunks to OpenAI when configured, and semantic queries send query text, even when text generation uses local LM Studio. Originals and extracted results remain under `POCKETTA_DATA_DIR` until deletion. API keys stay on the server; model-run records contain metadata rather than prompts or source content.

Initial installation requires internet. Cerebras mode also requires internet during generation and vision analysis; local text mode uses prepared LM Studio models. Local execution reduces disclosure risk but is not a formal security proof, and generated material can be incomplete or wrong. Browser tab recording currently depends on Chromium tab-capture behavior and requires the user to explicitly share tab audio. Inspect generated material's cited evidence.

The bundled 2.5-minute demo is an attributed excerpt of MIT OpenCourseWare material. Its CC BY-NC-SA licence and derivation are documented in [samples/README.md](samples/README.md); it is not relicensed under PocketTA's MIT code licence.

## Project documentation

- [Architecture](ARCHITECTURE.md)
- [Operations and offline acceptance](docs/README.md)
- [Demo runbook](docs/DEMO.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## Model and runtime attribution

| Component | Role | Licence/source | Included here? |
|---|---|---|---|
| PocketTA Local | Application | [MIT](LICENSE) | Yes |
| whisper.cpp | Speech runtime | [MIT](https://github.com/ggml-org/whisper.cpp/blob/master/LICENSE) | No |
| Whisper `base.en` | Speech model | [OpenAI Whisper](https://github.com/openai/whisper) | No |
| Qwen 3.5 4B | Study-pack model | [Apache-2.0 model card](https://huggingface.co/Qwen/Qwen3.5-4B) | No |
| LM Studio | Local model server | [LM Studio terms](https://lmstudio.ai/terms) | No |

Dependencies retain their own licences. Models and runtime binaries must be installed separately.
