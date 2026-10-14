# PocketTA demo run sheet

Target length: about 4 minutes. The Track D brief allows 3–10 minutes.

## Before recording

- Start the backend and frontend; confirm the health/readiness panel is green.
- Use a prepared course with indexed, synthetic or properly licensed material. Keep the source PDF and a generated quiz ready before recording so model latency does not dominate the video.
- Check that one supported question opens the intended citation and that one off-material question is refused. Rehearse the exact prompts once.
- Keep one completed quiz attempt available if live generation or grading is slow. Say when a screen shows a prepared result.
- Use a clean browser window, hide unrelated tabs and notifications, set readable zoom, and test microphone level and screen capture.
- PocketTA's default embeddings run locally without a paid embedding API. Text/vision model calls use the configured provider and may incur separate usage.

## Suggested narration and screen flow

### 0:00–0:25 · Problem and promise

“Course material is spread across recordings, slides, and readings. PocketTA turns it into a study workspace where answers link back to the source, and graded work guides what to practice next.”

Show the course workspace and its already processed course sources. If you did not process a recording during this capture, describe recording support as a capability and show its completed state only if you have a real prepared example.

### 0:25–0:55 · Course map and provenance

Open the topic hierarchy. Point out a major topic, a subtopic, a key concept, and a prerequisite link. Open a topic's source evidence to show the original page or slide location.

### 0:55–1:45 · Grounded tutor

Ask a question whose answer is explicit in the prepared source, for example: “What are the four necessary conditions for deadlock?” Show the concise answer and open its page citation. Then ask an unrelated question the course does not cover. Show the refusal and explain that unsupported or uncertain source material is not presented as a course-backed fact.

### 1:45–2:55 · Assessment and feedback

Open a prepared mixed quiz or generate one if the live provider is responding quickly. Show that questions carry topic and source references. Submit one or two answers, then show cited feedback and the post-assessment weak-topic or misconception report.

### 2:55–3:35 · Learner progress

Show the topic progress and next-step recommendation. Complete a tutor understanding check or show a saved graded check to demonstrate how graded evidence enters the mastery history. State accurately: “Tutor conversation activity is tracked by topic when cited material supports the topic; graded checks and quizzes update mastery.”

### 3:35–4:05 · Architecture and evidence

Briefly name React, FastAPI, and SQLite. Explain that embeddings default to local FastEmbed, while configured text or vision model requests are separate provider calls. State that evaluation uses small synthetic samples, that the same model family generated and judged some results, and that simulated learner gains are not real-world learning evidence.

## Recording guardrails

- Prefer one clean take with readable UI and steady narration over adding more features.
- Do not claim ordinary chat changes mastery; it updates conversation activity. Explicit graded checks and quiz answers update mastery.
- Do not claim real learner gains, broad transcription accuracy, or broad multimodal quality from the current synthetic checks.
- If a live request stalls, use the prepared result and identify it as prepared rather than implying it was generated during the recording.
- Watch the final video once, check audio and citation text at full screen size, then verify the YouTube link works signed out.
