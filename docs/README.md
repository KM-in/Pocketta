# PocketTA Local Operations

See [course tutor and citations](TUTOR.md), [knowledge retrieval](KNOWLEDGE.md) and [model and processing configuration](FOUNDATION.md) for cloud provider keys, model roles, cost tracking, scheduling, and smoke checks. The local/offline checklist below applies when cloud capabilities are not used.

## Native Preparation

Install FFmpeg using the operating system package manager. Build whisper.cpp into `vendor/whisper.cpp`, then place `ggml-base.en.bin` in `vendor/whisper.cpp/models`. The configured paths can be overridden in `.env` and must point to prepared local files.

`WHISPER_USE_GPU=false` is the reliable default. Enable it only after a native smoke test succeeds on the target GPU; PocketTA otherwise uses whisper.cpp's CPU backend.

For NVIDIA CUDA systems, PocketTA can auto-prefer Faster Whisper. Install it while online with:

```bash
.venv/bin/python -m pip install -r backend/requirements-faster-whisper.txt
```

Install the NVIDIA CUDA cuBLAS/cuDNN runtime libraries required by Faster Whisper for the target OS. If `FASTER_WHISPER_MODEL_PATH` points at a local CTranslate2 model directory, PocketTA uses that directory. Otherwise, prepare the configured model name, default `turbo`, while online:

```bash
.venv/bin/python -m backend.app.tools.prepare_faster_whisper
```

`TRANSCRIPTION_BACKEND=auto` uses Faster Whisper only when its package, CUDA runtime, and local/prepared model are ready; otherwise it falls back to whisper.cpp. Use `TRANSCRIPTION_BACKEND=faster_whisper` to require CUDA transcription, or `TRANSCRIPTION_BACKEND=whisper_cpp` to force the original path.

Install LM Studio, download Qwen 3.5 4B while online, and load it manually with a context length of at least 16K. Start the local server in LM Studio's Developer tab on `127.0.0.1:1234`. PocketTA checks `/v1/models` but never starts the server, loads a model, or downloads one.

PocketTA sends one generation request at a time, accepts LM Studio's structured content or reasoning-content response field, and rejects generated citations to uncertain transcript segments. Inputs above `GENERATION_CHUNK_CHARS` (or its legacy `LM_STUDIO_CHUNK_CHARS` alias) are summarized in chronological evidence-linked chunks before final generation.

The default request timeout is eight minutes because measured structured generation on the 8 GB reference machine can exceed six minutes for a 10-minute transcript.

The prepared reference machine uses model identifier `qwen3.5-4b`, whisper.cpp commit `080bbbe85230f624f0b52127f1ae1218247989f9`, and `base.en` SHA-256 `b7518e435da610821f88090732a6c5c685e9194edf1214b9d36a0eb9dff2051b`.

Windows uses the `.exe` whisper CLI path in `.env`. All application subprocess calls use argument arrays and portable paths rather than shell syntax.

## Browser Recording

Microphone recording uses the standard browser `MediaRecorder` and `getUserMedia` APIs. Browser tab audio recording currently works only in Chromium-based browsers such as Chrome and Edge because PocketTA relies on Chromium's tab-audio display-capture behavior.

For YouTube or another tab source:

1. Open PocketTA in Chrome or Edge.
2. Click **Record browser tab audio**.
3. In the browser share picker, choose the browser tab that is playing audio, not a window or full screen.
4. Enable **Share tab audio**.
5. Stop recording in PocketTA, preview the captured audio, then use the recording.

If the selected stream has no audio track, PocketTA stops the capture and explains whether the user selected a window/screen or forgot to enable tab audio.

## Data and Privacy

SQLite and lecture directories are stored below `POCKETTA_DATA_DIR`. Each UUID directory contains the original source and completed transcript/study-pack JSON. Normalized audio is temporary. `DELETE /api/lectures/{id}` cancels owned native work, deletes this directory, and removes its database row.

The application contains no CDN, telemetry, accounts, model downloader, or external vector database. Tutor history and check grades stay in local SQLite; configured model providers receive relevant evidence, questions, and submitted answers.

## Offline Acceptance Checklist

1. While online, complete project setup, build whisper.cpp, download `base.en`, optionally prepare Faster Whisper CUDA, and prepare Qwen in LM Studio.
2. Start LM Studio, load Qwen, start FastAPI and Vite, and confirm `/api/health` reports every component ready.
3. Disable Wi-Fi.
4. Upload a consented English recording under 200 MB.
5. Confirm the job reaches `completed`, uncertain transcript text is marked, and every generated item links to a real transcript segment.
6. If using CUDA, confirm `/api/health` reports `selected=faster_whisper`.
7. In Chrome or Edge, record a short browser tab sample with **Share tab audio** enabled and confirm it can be uploaded.
8. Correct one transcript segment, confirm the stale study pack disappears, and regenerate without rerunning transcription.
9. Export Markdown and verify its evidence links target the transcript appendix; test Print / Save as PDF.
10. Restart PocketTA and confirm the lecture persists.
11. Delete the lecture and verify both its UUID directory and SQLite row are gone.

Record OS, CPU, GPU, memory, selected transcription backend, whisper.cpp commit or Faster Whisper model, LM Studio version, recording duration, processing time, and peak memory for the hackathon demo.

## Benchmark Workflow

```bash
mkdir -p benchmark-results
.venv/bin/python scripts/benchmark.py /path/to/consented-sample.mp4 \
  --json-out benchmark-results/sample.json \
  --markdown-out benchmark-results/sample.md
```

Run once while connected to establish setup, then twice after disabling Wi-Fi. The runner refuses to begin unless readiness is green. Its poll-based stage timings are approximate; total time covers upload start through the terminal API response.

## Troubleshooting

- **FFmpeg/FFprobe missing:** run the command shown in readiness, then restart FastAPI.
- **whisper.cpp missing:** build the pinned checkout and verify `WHISPER_CLI_PATH` and `WHISPER_MODEL_PATH`.
- **Faster Whisper unavailable:** install the optional requirements and CUDA libraries, prepare the configured model while online, or set `TRANSCRIPTION_BACKEND=whisper_cpp`.
- **LM Studio unavailable:** load Qwen 3.5 4B with a 16K context, start the Developer server, and copy its exact `/v1/models` ID into `.env`.
- **Transcript exists but generation failed:** ensure the loaded model supports JSON-schema output and that reliable speech remains after uncertainty filtering.
- **Generation failed after transcription:** use "Generate study pack" to retry from the saved transcript.
- **Recording rejected after upload:** convert corrupt media to WAV/MP3 or use a file under the upload size limit.
- **Browser tab recording has no audio:** use Chrome or Edge, select the browser tab itself rather than a window or screen, and enable "Share tab audio" in the share picker.
- **Browser tab recording is unavailable:** Firefox and Safari do not currently provide the required Chromium-compatible tab-audio capture path; use microphone recording or upload a file instead.
