# Local native media integration checks · 13 October 2026

These checks use disposable synthetic files. No course documents or user media were used.

## Legacy PowerPoint conversion

`backend/tests/test_legacy_ppt_integration.py` creates a two-slide PPTX, converts it to legacy `.ppt` with LibreOffice, then runs that `.ppt` through `DocumentProcessor`. The service converts it back to PPTX and PDF, extracts text, indexes it, and reaches `ready` with `slide:1` and `slide:2` provenance. Both slide excerpts matched the known synthetic text, and the rendered PDF contained two pages. The local runtime reported LibreOfficeDev 26.8.0.0.alpha0; this validates this machine's conversion path, not every PowerPoint feature or another LibreOffice release.

## Video frame sampling

`backend/tests/test_media_integration.py` creates a 65-second synthetic 1-fps video with FFmpeg and checks real frame files and dimensions. The first run exposed a seek at 64.5 seconds, where a 1-fps recording has no frame. Sampling now leaves one second at the end; the integration check returns frames at 0 and 64,000 ms, both 1280×720. The local FFmpeg runtime is 8.1.2.

## Browser video seek

On the synthetic 61-second recording below, the full source page loaded the cited 60-second frame after the media element's metadata became available. In the browser, the video reported `readyState=4`, `duration=61`, and `currentTime=60`. This verifies end-to-end timestamp navigation for this local synthetic recording; it does not cover every browser/codec combination.

## Synthetic live-provider end-to-end check · 14 October 2026

After fixing PDFium image geometry to use the installed library's `get_pos()` API, a one-page synthetic raster diagram was uploaded through the FastAPI application in a temporary data directory. The configured Cerebras text/vision provider transcribed the diagram labels and explanatory text; checks found both “ready queue” and “quantum.” Indexing produced five hierarchy entries (one major topic, two subtopics, and two key concepts), and a natural-language retrieval query returned a cited source item. No existing course material was used.

The same temporary synthetic course generated a two-question MCQ quiz. Both answers were intentionally wrong; submission completed and persisted an assessment report with two weak topics, two likely-misconception entries, and question IDs that resolved to source citations when the report was reopened. This confirms live provider and API behavior on synthetic material. It does not verify video transcription/frame analysis, browser timestamp seeking, or visual presentation in a browser.

## Synthetic lecture-video frame and citation check · 14 October 2026

A generated 61-second MP4 with a static educational diagram passed through the recording API and FFmpeg frame sampler. For this isolated check, the transcription method returned a hand-written synthetic transcript because this checkout has neither the configured Whisper binary/model nor Faster Whisper installed. The normal frame-description, topic indexing, and source retrieval code called the configured Cerebras provider. The completed course source retained both frame units after reindexing; retrieval returned frame citations at 0 and 60 seconds, and the frame descriptions included “ready queue.”

This run exposed and fixed two recording integration bugs: `processor.py` used `json.dumps` without importing `json`, and transcript synchronization deleted visual frame units before knowledge indexing. It also exposed that recording status updates changed the legacy lecture row but left the course source row stuck at “queued”; status and progress now stay synchronized.

The same synthetic recording was then opened in the browser at its cited 60-second frame. After metadata loaded, the video element reached `readyState=4`, reported a 61-second duration, and had `currentTime=60`; the 0-second and 60-second frame citations remain available from the source index.

## Local Whisper recording upload-to-transcript check · 14 October 2026

A short synthetic lecture MP4 with locally synthesized speech was uploaded through `POST /api/lectures`. The application worker extracted and normalized its audio with FFmpeg, transcribed it with whisper.cpp `1.9.4` and the local `base.en` model, persisted the transcript, and returned it through the lecture API. The check also confirmed the processing job completed and removed its temporary normalized WAV. The generated speech contained no personal recording; no cloud transcription, model-generation, vision, or embedding API was called. The transcript contained the expected terms “process,” “program,” “stack,” and “registers.” This validates the real runtime path on one short synthetic sample, not broad speech-recognition accuracy. Reproduce it with the command in [the transcription fixture notes](../../backend/tests/fixtures/README.md).
