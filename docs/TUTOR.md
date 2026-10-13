# Course tutor and citation flow

Open a course and choose **Course tutor**. Choose Explain simply, Give an example, Compare concepts, or Test my understanding. A configured text engine is required for generation, verification, and grading. `VERIFIER_MODEL` and `GRADER_MODEL` can override the selected text model; otherwise the same model performs separate requests. Retrieval works with keyword search when OpenAI embeddings are unavailable.

Each question retrieves an `EvidenceBundle` from the active course. Short follow-ups also include the preceding question in the retrieval query. Previous questions help interpret the request; previous generated answers are never evidence. Generation emits only bounded claims with exact retrieved chunk IDs. The backend validates membership, then makes a separate verification request that judges each claim against its **cited excerpts**, checks relevance, and rejects unsupported extrapolation. Every claim must receive a distinct supported verdict with confidence at least 0.8. Missing or weak verdicts produce a refusal. Engine failures return an actionable error without publishing an unverified answer.

For an explicit understanding check, generation also produces a short-answer question, expected answer, rubric, and citations. Verification checks support and ambiguity before publishing the question. The expected answer and rubric stay server-side. The grading gateway receives that same question, rubric, expected answer, and exact saved evidence. Grades below 0.8 confidence are marked uncertain. One submission is saved per check; generating another check permits further practice. Ordinary chat turns have no response or grade and cannot be submitted as checks.

SQLite `tutor_turns` stores the question, intent, verified claims, used citation snapshots, source versions, verifier result, private check, response, grade, and timestamps. The local MVP has one learner identity (`local`), with separate history per course. A graded explicit check adds a reliable or uncertain topic observation to the same BKT history used by quizzes; ordinary chat never updates mastery. Check observations use the most common topic tag among their cited chunks. If the evidence has no topic tag, they use a shared fallback topic rather than treating each question as a new topic.

Before publishing an answer or saving a grade, a write transaction revalidates chunk IDs, course membership, original text offsets, source versions, uncertainty, locations, and index freshness. Source edits, moves, or deletion during model calls cannot publish stale content. Saved history remains a historical record; opening a removed, uncertain, stale, or changed-version citation displays an error.

## Navigation

Tutor, course search, and source study-pack citations use the shared evidence links. Links carry course, source, unit, and source version. A course-scoped resolver validates the destination before displaying it:

- PDF citations open an embedded original PDF at `#page=N`, with a new-tab link.
- PPTX citations open the converted PDF at the original slide number.
- Recording citations load the original audio/video in a native HTML media player and set `currentTime` to the exact citation timestamp after metadata loads. Transcript segments are also focused.

Native PDF viewing and audio/video decoding depend on browser support for the uploaded format. Local transcription can support formats the browser cannot play. No new codec conversion or visual-frame extraction is included in this section.

## API

- `GET /api/courses/{course_id}/tutor`: saved conversation.
- `POST /api/courses/{course_id}/tutor`: `{ "question": "Explain deadlock", "intent": "explain" }`; intents are `explain`, `example`, `compare`, `check`.
- `POST /api/courses/{course_id}/tutor/{turn_id}/answer`: `{ "response": "My answer" }`; explicit unanswered checks only.
- `GET /api/courses/{course_id}/citations/{unit_id}?version=1`: validated citation location and source metadata. The original unscoped resolver remains for compatibility; tutor/navigation use the scoped route.

## Validation and limits

Run `.venv/bin/python -m pytest -q`, `npm --prefix frontend test`, and `npm --prefix frontend run build` from the repository root. Tests exercise real SQLite retrieval and persistence with mocked model outputs, including valid-ID unsupported claims, absent verdicts, low confidence, refusals, source edits/deletes/moves during verification, course isolation, private rubrics, single submissions, uncertain grades, exact timestamp seeking, and PDF/slide navigation.

The verifier is a model judgment, not a proof of truth. Confidence is a configured gate on model-reported confidence, not a calibrated probability. Quiz and explicit tutor-check grades update the per-topic BKT learner estimate; ordinary chat does not. Video frame descriptions are indexed as timestamped evidence when the Cerebras vision provider is configured. Live provider faithfulness, real browser codec playback, real LibreOffice conversion, and simulated multi-session learner outcomes still require evaluation.
