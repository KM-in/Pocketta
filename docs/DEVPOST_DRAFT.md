# Devpost draft — PocketTA

**Status:** Draft only. Add the recorded demo URL before submission. Verify every claim against the final deployed build.

## Project details

- **Project name:** PocketTA
- **Track:** D — Personalized Tutoring & Adaptive Learning
- **Team members and Devpost accounts:** Kartik Mishra (`mishrakartik2007`); Kartikeya Srivastava (`kartik-sri769`)
- **Demo video (3–10 minutes):** Pending recording; no video has been recorded yet
- **Source repository:** https://github.com/KM-in/pocketta-local

## Short description

PocketTA turns a student's course files into a source-cited tutor and adaptive study workflow. It connects explanations and assessments to the uploaded pages, slides, and lecture timestamps, then uses graded evidence to guide what the student should practice next.

## Problem

Students often divide a course among lecture recordings, textbooks, and slide decks. General-purpose chat tools can answer without showing which course material supports the answer, and a static quiz does not adapt to what a student has demonstrated. That makes it difficult to trust explanations or decide what to study next.

## Solution

PocketTA organizes uploaded material into a course knowledge base with source provenance. Students can ask questions and open citations at their original page, slide, or recording timestamp. When course evidence is missing or weak, the tutor can refuse instead of presenting an unsupported answer as course fact.

Students can generate mixed assessments with multiple-choice, short-answer, and numerical questions. Verified questions cite course evidence and carry topic and difficulty tags. Attempts are saved; multiple-choice and numerical answers are checked deterministically, while short answers are graded against a rubric and retrieved evidence. Each completed attempt gives a cited report of weak topics and likely misconceptions inferred from missed answers, with a cautious fallback when a model review is unavailable. New learners can start a short diagnostic from the course material. Reliable grades update a topic-level Bayesian Knowledge Tracing estimate. The dashboard shows evidence counts, recent mistakes, and practice recommendations, and labels topics with too little evidence as insufficient rather than presenting a confident mastery score.

## How it works

The web client uses React and TypeScript. A FastAPI service coordinates ingestion, retrieval, tutoring, assessments, and saved learner history in SQLite. PDFs and slide decks preserve page or slide provenance; recordings are transcribed locally and video frames can be indexed with timestamped visual descriptions when a vision provider is configured. Hybrid retrieval combines keyword search with optional embeddings. A model gateway separates provider configuration from the application workflows. Claims and questions go through separate verification steps before they are saved or shown.

The learner model uses transparent MVP BKT parameters rather than parameters fitted to a real student dataset. It excludes uncertain grades and requires repeated reliable evidence before displaying mastery. Ordinary tutor chat is not counted as evidence; explicit understanding checks and graded assessment answers are.

## What is novel

PocketTA joins provenance-preserving multimodal course ingestion, claim-level tutor checks, verified question generation, resumable assessment attempts, and a persistent topic model in one workflow. Its practical focus is traceability: the same course evidence used to retrieve an answer can be opened by a learner, cited in an assessment, and used to explain why a recommendation appears. The system presents learner mastery as an estimate with evidence and uncertainty, not as a direct measurement of learning.

## Evaluation

On a small synthetic operating-systems fixture using offline keyword retrieval, the smoke evaluation retrieved all 6 expected source locations, with mean context precision **0.639** and mean context recall **1.000**. Both unsupported queries returned no evidence (**2/2**). A live DeepEval run with Cerebras on the same fixture scored faithfulness **1.000**, answer relevancy **0.972**, context precision **0.972**, and recall **1.000**. After clearing tutor history between independent fixture questions, it answered **6/6** supported questions and correctly refused both unsupported questions (**2/2**). A separate three-repeat coverage evaluation answered **17/18 (94.4%)** supported attempts, with one question answered in two of three attempts. These are small synthetic evaluations; the same model family generated and judged answers, and results do not establish broad retrieval quality, independently validated generated-question correctness, or learning gains.

With local FastEmbed embeddings enabled, a separate hybrid retrieval smoke test on the same fixture returned all six expected locations and rejected both unsupported queries (**2/2**) at the local similarity threshold of **0.80**. Semantic retrieval contributed candidates for two of the six supported queries; keyword fallback supplied the others. This test does not establish broad semantic retrieval quality. The run is preserved in [the FastEmbed report](evaluation/live-retrieval-fastembed-2026-10-14.json).

A separate question-quality smoke generated and saved eight MCQs through the production quiz pipeline. A same-model judge scored correctness **1.000**, clarity **0.988**, single-best-answer quality **1.000**, and cited-evidence support **1.000** in the stricter-verifier follow-up; it found **0/28** exact or near-duplicate pairs among accepted prompts. The baseline had flagged one potentially defensible distractor, so the production verifier now explicitly rejects MCQs without exactly one defensible answer. These scores are estimates from a small synthetic sample, not independent human labels. See [the question-quality report](evaluation/question-quality.md).

A deterministic toy simulation compared adaptive topic/difficulty selection with a fixed medium-difficulty topic rotation over three hand-authored learner profiles and six sessions each. Across 90 simulated questions per strategy, adaptive selection produced **0.567 vs 0.544** response accuracy, **0.204 vs 0.196** mean simulated skill gain, and **0.633 vs 0.867** repeated topic/difficulty-pair rate. A second simulator now runs 180 attempts through PocketTA's saved quiz and grading path using 12 hand-authored source-backed items. It produced tied average simulated accuracy (**0.544** each), mean skill gain **0.211 vs 0.196**, and exact saved-question ID repetition **0.633 vs 0.867**. Both simulations use programmed learner profiles and learning assumptions; neither is evidence of real learning. The second simulation does not evaluate model-generated question quality.

The per-case DeepEval results and limitations are documented in [the evaluation report](evaluation/track-d-deepeval.md), with [three-repeat answer-coverage results](evaluation/tutor-coverage.md). The independent question-review packet and [held-out learner pilot protocol](evaluation/held-out-learner-protocol.md) are ready, but human ratings and participant data still need to be collected.

## Demo outline

Record a 3–10 minute walkthrough showing: upload and processing of course sources; a supported question with an opened citation; an unsupported question and refusal; a mixed assessment and feedback; a saved mastery update and next-step recommendation; and the architecture and evaluation limitations. Show the live configured flow and identify any prepared examples. Add the public or unlisted YouTube link here after recording.

## Submission checklist

- [x] Add the Devpost usernames for Kartik Mishra and Kartikeya Srivastava.
- [ ] Record and review the demo; verify the link works signed out.
- [x] Backend dependency consistency is clean (`pip check`); all 150 backend tests pass, 47 frontend tests pass, and the production build succeeds.
- [x] Run a live local-embedding retrieval smoke test with zero paid embedding API calls; the report records semantic and keyword-fallback coverage separately.
- [x] Validate the configured provider flow on synthetic PDF and video material and the real legacy PPT conversion path. The video integration run used a synthetic transcript because no local Whisper runtime/model is installed.
- [x] Verify recording timestamp navigation in the browser after media metadata loads: the synthetic 61-second video sought to its cited 60-second frame. This checks the local browser/media path, not every codec or browser.
- [x] Run and publish a framework-based evaluation on the documented synthetic test set; see its coverage and limitations above.
- [ ] Collect two independent reviews for the 14-item question-quality packet in [the human-review protocol](evaluation/human-question-review.md), then report the labels separately from model-judge scores.
- [ ] Run the deidentified [held-out learner pilot](evaluation/held-out-learner-protocol.md) and report the results as an exploratory study.
- [x] Cross-check the numeric evaluation claims against their saved JSON results and the feature claims against the current local implementation.
- [ ] Publish the reviewed code state to the public source repository; it is committed locally on `codex/track-d-submission-readiness` but has not been pushed.
- [ ] Review screenshots and confirm the deployed build matches the reviewed local build before submission.
- [ ] Submit the completed entry through the team's Devpost account.
