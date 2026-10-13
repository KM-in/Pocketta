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

Students can generate mixed assessments with multiple-choice, short-answer, and numerical questions. Verified questions cite course evidence and carry topic and difficulty tags. Attempts are saved; multiple-choice and numerical answers are checked deterministically, while short answers are graded against a rubric and retrieved evidence. Reliable grades update a topic-level Bayesian Knowledge Tracing estimate. The dashboard shows evidence counts, recent mistakes, and practice recommendations, and labels topics with too little evidence as insufficient rather than presenting a confident mastery score.

## How it works

The web client uses React and TypeScript. A FastAPI service coordinates ingestion, retrieval, tutoring, assessments, and saved learner history in SQLite. PDFs and slide decks preserve page or slide provenance; recordings are transcribed locally and video frames can be indexed with timestamped visual descriptions when a vision provider is configured. Hybrid retrieval combines keyword search with optional embeddings. A model gateway separates provider configuration from the application workflows. Claims and questions go through separate verification steps before they are saved or shown.

The learner model uses transparent MVP BKT parameters rather than parameters fitted to a real student dataset. It excludes uncertain grades and requires repeated reliable evidence before displaying mastery. Ordinary tutor chat is not counted as evidence; explicit understanding checks and graded assessment answers are.

## What is novel

PocketTA joins provenance-preserving multimodal course ingestion, claim-level tutor checks, verified question generation, resumable assessment attempts, and a persistent topic model in one workflow. Its practical focus is traceability: the same course evidence used to retrieve an answer can be opened by a learner, cited in an assessment, and used to explain why a recommendation appears. The system presents learner mastery as an estimate with evidence and uncertainty, not as a direct measurement of learning.

## Evaluation

On a small synthetic operating-systems fixture using offline keyword retrieval, the smoke evaluation retrieved all 6 expected source locations, with mean context precision **0.639** and mean context recall **1.000**. Both unsupported queries returned no evidence (**2/2**). A live DeepEval run with Cerebras on the same fixture scored faithfulness **1.000** and answer relevancy **0.969** across the **4** supported questions the tutor answered; context precision was **0.972** and recall **1.000** across all **6** supported questions. In that run, the tutor answered **4/6 (66.7%)** supported questions and refused two despite retrieved evidence. It correctly refused both unsupported questions (**2/2**). An isolated replay later answered and verified one of those two questions, so the single-run coverage is not a stability estimate. This is a small synthetic evaluation; the same model generated and judged answers, and results do not establish live semantic-search performance, independently validated generated-question correctness, or learning gains.

A separate question-quality smoke generated and saved eight MCQs through the production quiz pipeline. A same-model judge scored correctness **1.000**, clarity **0.988**, single-best-answer quality **1.000**, and cited-evidence support **1.000** in the stricter-verifier follow-up; it found **0/28** exact or near-duplicate pairs among accepted prompts. The baseline had flagged one potentially defensible distractor, so the production verifier now explicitly rejects MCQs without exactly one defensible answer. These scores are estimates from a small synthetic sample, not independent human labels. See [the question-quality report](evaluation/question-quality.md).

A deterministic toy simulation compared adaptive topic/difficulty selection with a fixed medium-difficulty topic rotation over three hand-authored learner profiles and six sessions each. Across 90 simulated questions per strategy, adaptive selection produced **0.567 vs 0.544** response accuracy, **0.204 vs 0.196** mean simulated skill gain, and **0.633 vs 0.867** repeated topic/difficulty-pair rate. A second simulator now runs 180 attempts through PocketTA's saved quiz and grading path using 12 hand-authored source-backed items. It produced tied average simulated accuracy (**0.544** each), mean skill gain **0.211 vs 0.196**, and exact saved-question ID repetition **0.633 vs 0.867**. Both simulations use programmed learner profiles and learning assumptions; neither is evidence of real learning. The second simulation does not evaluate model-generated question quality.

The per-case DeepEval results and limitations are documented in [the evaluation report](evaluation/track-d-deepeval.md). A larger independently labeled question set and repeated-run tutor answer-coverage evaluation remain before submission.

## Demo outline

Record a 3–10 minute walkthrough showing: upload and processing of course sources; a supported question with an opened citation; an unsupported question and refusal; a mixed assessment and feedback; a saved mastery update and next-step recommendation; and the architecture and evaluation limitations. Show the live configured flow and identify any prepared examples. Add the public or unlisted YouTube link here after recording.

## Submission checklist

- [x] Add the Devpost usernames for Kartik Mishra and Kartikeya Srivastava.
- [ ] Record and review the demo; verify the link works signed out.
- [x] Backend dependencies verified (`pip check` clean), all 140 backend tests pass, 46 frontend tests pass, and the production build succeeds.
- [ ] Validate the configured provider flow, real legacy PPT conversion, and video timestamp navigation.
- [x] Run and publish a framework-based evaluation on the documented synthetic test set; see its coverage and limitations above.
- [ ] Review all metrics, screenshots, and claims against the final build.
- [ ] Submit the completed entry through the team's Devpost account.
