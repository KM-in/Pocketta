# Multimodal AI Hackathon 2026 · Track D status

Reviewed on 13 October 2026 against the Track D brief. The work is published on GitHub `main` at `a5a9b90` (`Complete Track D hackathon submission work`). This status does not claim a live-provider evaluation or public demo.

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
- Run the new [DeepEval Track D evaluator](evaluation/track-d-deepeval.md) to measure tutor faithfulness, answer relevancy, and context precision/recall against actual tutor output and cited synthetic excerpts. The evaluator is implemented but no scores are available yet: the one-case smoke reached Cerebras and returned HTTP 402. Then evaluate question correctness/ambiguity and repetition rate with a labeled question set.
- Measure question correctness, ambiguity, and generation novelty with model-generated assessment items. A new six-session simulation now uses source-backed hand-authored saved questions and the production attempt/grading/SQLite learner-history path; its deterministic synthetic comparison is documented separately. It validates pipeline persistence and exact saved-question reuse only, not generated-item quality or real learner gains.
- Exercise live model roles, video-frame vision analysis/retrieval, and browser-video seeking. Local native integration checks now pass for actual legacy PPT → PPTX/PDF conversion with slide provenance and for low-frame-rate FFmpeg frame sampling; results and limits are in [the integration report](evaluation/real-integration-checks.md).
- Confirm the learning dashboard's session history and prerequisite recommendation in the full app after integration testing.
- Test/setup gate: the project venv has its declared NumPy and optional DeepEval dependencies installed; `pip check` reports no broken requirements. The full backend suite passes with all 139 tests. In this restricted runner, `pytest -p no:rerunfailures` is needed because that optional plugin binds a localhost socket, which the sandbox denies. On latest `main`, frontend verification passes with 46 tests and a production build.
- The DeepEval adapter and evaluation dependency are isolated from runtime requirements. A live model run needs usable Cerebras inference credit; live semantic retrieval also needs an embedding API key or local endpoint.
- Record a 3–10 minute YouTube demo with English audio or subtitles using the walkthrough in [the demo runbook](DEMO.md). Check signed-out access.
- Add Devpost usernames for Kartik Mishra and Kartikeya Srivastava, then submit the completed [Devpost draft](DEVPOST_DRAFT.md) with the demo link.

## Submission handoff

The source repository is public and the submission work is published on `main` at `a5a9b90`. The demo video and Devpost submission are not present in this repository. Kartik Mishra and Kartikeya Srivastava are the supplied team member names; their Devpost usernames are still needed. Remaining gates include successful live-provider evaluation, real configured-flow checks, demo recording, and completing the Devpost entry. See the remaining verification gates above before describing the project as submission-ready.
