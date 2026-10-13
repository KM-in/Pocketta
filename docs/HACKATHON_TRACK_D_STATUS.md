# Multimodal AI Hackathon 2026 · Track D status

Reviewed on 14 October 2026 against the Track D brief. The work is published on the public GitHub `main` branch. A live text tutor/judge evaluation is now recorded; multimodal live checks and a public demo are still outstanding.

## Implemented in the prototype

- Course ingestion for PDF, PPTX, legacy PPT, and recordings. PDF/PPT/PPTX pages or slides retain provenance; legacy PPT converts to PPTX and PDF through LibreOffice with a slide-count check. Recordings transcribe locally. With Cerebras vision configured, up to 20 evenly spaced video frames are described, saved with uncertainty and timestamp, and indexed with the transcript.
- Provenance-preserving course chunks, keyword and semantic retrieval, topic tags, prerequisite links, and a held-out synthetic OS fixture with known source locations and unsupported questions.
- Tutor answers retrieve from the active course, require claim-level citation verification, open exact pages/slides/timestamps, and refuse when evidence is missing. Explicit tutor checks are graded and saved; ordinary chat does not alter mastery.
- Verified assessment bank with MCQ, short-answer, and numerical items; topics, difficulty, citations, and question version; deterministic MCQ/numerical grading; evidence-based short-answer grading; saved resumable attempts; and exact/near-duplicate prompt rejection.
- Per-course local learner history, topic-level Bayesian Knowledge Tracing (BKT), uncertain-grade exclusion, assessment history, weak-topic targeting, and insufficient-evidence display. Parameters and limitations are documented in [multi-source assessment](MULTI_SOURCE.md).
- Optional syllabus mapping, source-backed progress, recent mistakes, and a learning-history report.
- Setup, model boundary, retrieval, tutor, and demo walkthrough documentation. The GitHub repository `KM-in/pocketta-local` was checked through the GitHub repository API and reports `visibility=public`, with `main` as its default branch.

## Still needed for a strong submission

- Measure semantic retrieval and rerun context precision/recall after final edits. The offline keyword result is documented in [the evaluation report](evaluation/track-d-retrieval-2026-10-13.md); its context precision is 0.639 on six supported synthetic queries, with 1.000 recall and 2/2 unsupported refusals. A live-embedding run is unavailable because this checkout has no embedding API key or local embedding endpoint; the evaluation command now reports that configuration error instead of silently claiming a live run.
- A live [DeepEval Track D evaluation](evaluation/track-d-deepeval.md) now covers all six supported and two unsupported synthetic questions. Faithfulness was 1.000 and answer relevancy 0.969 over the four supported questions answered; context precision was 0.972 and recall 1.000 over all six; both unsupported questions were refused. The tutor also refused two answerable questions, so supported answer coverage was 4/6 (66.7%). Scores are model-based estimates from the same generation/judge model and the synthetic fixture is small. Generated-question correctness/ambiguity, repetition rate, and stronger answer coverage still need evaluation.
- Measure question correctness, ambiguity, and generation novelty with model-generated assessment items. A new six-session simulation now uses source-backed hand-authored saved questions and the production attempt/grading/SQLite learner-history path; its deterministic synthetic comparison is documented separately. It validates pipeline persistence and exact saved-question reuse only, not generated-item quality or real learner gains.
- Exercise live model roles beyond text tutoring/judging, video-frame vision analysis/retrieval, and browser-video seeking. Local native integration checks pass for actual legacy PPT → PPTX/PDF conversion with slide provenance and for low-frame-rate FFmpeg frame sampling; results and limits are in [the integration report](evaluation/real-integration-checks.md).
- Confirm the learning dashboard's session history and prerequisite recommendation in the full app after integration testing.
- Test/setup gate: the project venv has its declared NumPy and optional DeepEval dependencies installed; `pip check` reports no broken requirements. The full backend suite passes with all 139 tests. In this restricted runner, `pytest -p no:rerunfailures` is needed because that optional plugin binds a localhost socket, which the sandbox denies. On latest `main`, frontend verification passes with 46 tests and a production build.
- The DeepEval adapter and evaluation dependency are isolated from runtime requirements. Cerebras text tutoring and judge calls succeeded in the recorded evaluation. Live semantic retrieval still needs an embedding API key or local endpoint.
- Record a 3–10 minute YouTube demo with English audio or subtitles using the walkthrough in [the demo runbook](DEMO.md). Check signed-out access.
- The Devpost usernames are recorded in the [draft](DEVPOST_DRAFT.md). Add the demo link and submit the completed entry.

## Submission handoff

The source repository is public and the submission work is published on `main`. The team member names and Devpost usernames are recorded in the draft; the demo video and Devpost submission are not yet present. Remaining gates include generated-question quality and held-out learning evaluation, semantic embedding and multimodal/browser flow checks, demo recording, and completing the Devpost entry. See the remaining verification gates above before describing the project as submission-ready.
