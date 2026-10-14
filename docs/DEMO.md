# Track D submission demo runbook

Record a 5–7 minute walkthrough with an English voice track or English subtitles. Use a public-domain or team-created OS course chapter, slides, and video. Keep any prepared example clearly labelled; do not imply it was processed live.

## Before recording

- Start FastAPI and the React app. Configure the selected text provider and embedding provider; use Cerebras vision if demonstrating PDF diagrams or video frames. Confirm `/api/health` reports the intended configuration.
- Prepare one PDF chapter, one PPT/PPTX deck, and a short video with consent/public reuse. Wait for all three sources to finish extraction and indexing.
- Add an OS syllabus or use the course topics. Confirm topic/source mappings. Prepare two known-answer questions and one question outside the uploaded material.
- Open browser developer tools if discussing privacy. Explain that transcription is local; configured cloud text, vision, and embedding requests send the specific excerpts, frames, or query text described in [model configuration](FOUNDATION.md).
- Have the evaluation report ready, labelled synthetic/offline or live-provider with its actual settings and limitations.

## Suggested 5–7 minute flow

1. **Problem and architecture (45 sec):** introduce scattered lecture, textbook, and slide material; show the React, FastAPI, SQLite, retrieval, model gateway, and local transcription boundary.
2. **Multimodal upload (60 sec):** upload a PDF, legacy PPT, and video; show extraction/index status, a slide or page preview, and timestamped transcript/frame evidence. Open a selected frame citation to seek the original video.
3. **Grounded tutor (60 sec):** ask a supported question, open its page/slide/timestamp citations, then ask an unsupported question and show the refusal.
4. **Assessment (90 sec):** generate a mixed quiz with MCQ, short answer, and numerical questions. Show topic, difficulty, and citations; complete an attempt and point out deterministic MCQ/numerical grading and rubric-based short-answer feedback.
5. **Learning loop (60 sec):** show saved attempts, topic mastery estimate, observation count, recent mistakes, and “insufficient evidence” for a new topic. Run a second session with an adaptive quiz and explain the BKT assumptions.
6. **Evaluation and limits (45 sec):** report the held-out retrieval and live DeepEval results: the independent-case run answered 6/6 supported questions, and a separate three-repeat coverage run answered 17/18 attempts. Include the generated-question quality smoke scores. State clearly that the same model family generated and judged answers/questions, coverage varied across a small sample, and the synthetic fixture and simulations are not proof of learning.
7. **Submission close (20 sec):** show setup instructions, repository, and the Devpost project URL once these are published.

## Release gate

- [x] Backend tests, frontend tests, and production build pass (146 backend and 47 frontend tests; production build succeeds).
- [ ] Live configured-provider flow works for supported and unsupported questions.
- [ ] Real LibreOffice conversion works for PPT and PPTX, with matching slide counts.
- [ ] Video extraction, vision descriptions, retrieval, and timestamp navigation work on the chosen sample.
- [ ] Assessment, retry-safe grading, BKT updates, and returning-learner behavior are shown from saved data.
- [ ] New-learner baseline diagnostic, inferred course hierarchy, and cited post-assessment misconception report are reviewed in the full app.
- [ ] Evaluation methods, fixture, provider/model versions, results, and limitations are published with the project.
- [ ] No private media, weights, `.env`, database, or machine-specific output is staged.
- [ ] YouTube link is public or unlisted and accessible signed out; Devpost links and team accounts are complete.

The local repository can prepare and document the walkthrough. Publishing the video and Devpost entry requires the team's account details and final approval of the recorded material.
