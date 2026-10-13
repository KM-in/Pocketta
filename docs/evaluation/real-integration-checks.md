# Local native media integration checks · 13 October 2026

These checks use disposable synthetic files. No course documents or user media were used.

## Legacy PowerPoint conversion

`backend/tests/test_legacy_ppt_integration.py` creates a two-slide PPTX, converts it to legacy `.ppt` with LibreOffice, then runs that `.ppt` through `DocumentProcessor`. The service converts it back to PPTX and PDF, extracts text, indexes it, and reaches `ready` with `slide:1` and `slide:2` provenance. Both slide excerpts matched the known synthetic text, and the rendered PDF contained two pages. The local runtime reported LibreOfficeDev 26.8.0.0.alpha0; this validates this machine's conversion path, not every PowerPoint feature or another LibreOffice release.

## Video frame sampling

`backend/tests/test_media_integration.py` creates a 65-second synthetic 1-fps video with FFmpeg and checks real frame files and dimensions. The first run exposed a seek at 64.5 seconds, where a 1-fps recording has no frame. Sampling now leaves one second at the end; the integration check returns frames at 0 and 64,000 ms, both 1280×720. The local FFmpeg runtime is 8.1.2.

## Still unverified

These checks do not call the configured vision model, test frame-description retrieval, or open the player in a browser to verify seeking after metadata loads. The configured Cerebras endpoint returned HTTP 402 during the separate DeepEval tutor smoke run, so live visual analysis also remains unverified.
