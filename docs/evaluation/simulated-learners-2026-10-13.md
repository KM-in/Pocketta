# Synthetic learner comparison · 13 October 2026

## Method

Ran `python3 -m backend.app.tools.simulate_learners` with a fixed seed. Three hand-authored ability profiles answered 30 questions each over six sessions. Adaptive topic selection used the current BKT formula, choosing the lowest estimated topic and selecting easy/medium/challenging levels by posterior thresholds. The comparison baseline rotated through topics at medium difficulty. Simulated response probability was the profile's latent topic skill adjusted by difficulty; latent skill rose by 0.035 after a correct answer and 0.020 after an incorrect answer.

## Results

| Metric | Adaptive | Fixed topic + medium |
|---|---:|---:|
| Simulated response accuracy | 0.567 | 0.544 |
| Mean latent skill gain | 0.204 | 0.196 |
| Repeated topic/difficulty pairs | 0.633 | 0.867 |

Each strategy answered 90 simulated questions total. The uneven learner had equal simulated accuracy under both strategies; the returning learner's simulated accuracy was slightly higher with the fixed baseline. Results vary by profile.

## Limits

This toy simulator hard-codes learner abilities, response probabilities, learning gains, question difficulty, and a synthetic question-template identity represented only by `(topic, difficulty)`. Its pair repetition metric is **not** an exact duplicate-question rate. It does not call the app's saved-question generation/attempt path and does not establish educational improvement or calibrated BKT parameters. The team should replace it with a source-backed, multi-session simulation using actual question records and report observed limitations.

## Saved-question and attempt-path simulation

Ran `python3 -m backend.app.tools.simulate_saved_learners --output docs/evaluation/saved-learner-attempts-2026-10-13.json`. This second deterministic simulation preloads 12 hand-authored MCQs, each tied to a retrieved synthetic source excerpt, into SQLite as saved quizzes. Three learner profiles then complete six sessions of five questions under both adaptive and fixed-topic policies. Each answer uses the app's `QuizService.create_attempt`, `save_answers`, and `submit` methods; grading is deterministic MCQ scoring, and the simulator checks that all 180 resulting topic observations were persisted. A regression test reruns these flows at [test_saved_learner_simulation.py](../../backend/tests/test_saved_learner_simulation.py).

| Mean across three simulated profiles | Adaptive | Fixed topic + medium |
|---|---:|---:|
| Simulated accuracy | 0.544 | 0.544 |
| Mean latent skill gain | 0.211 | 0.196 |
| Exact saved-question ID repetition | 0.633 | 0.867 |
| Topic/difficulty-pair repetition | 0.633 | 0.867 |

The new output is in [saved-learner-attempts-2026-10-13.json](saved-learner-attempts-2026-10-13.json). The adaptive policy reduces repeated question IDs in this finite question bank; accuracy is tied on average, and individual profiles differ. Questions are hand-authored and inserted as ready fixture quizzes, so this does not validate the model's question-generation or verification quality. The profiles, simulated answers, difficulty effects, and skill gains are programmed assumptions. It exercises attempt persistence and BKT updates, but is not evidence of real learning gains or a calibrated learner model.

The 12-item simulator bank passed deterministic fixture checks: every correct key is present among its options, each cited retrieved excerpt contains its designated fact, and all prompts and IDs are unique. These checks only validate this hand-authored benchmark bank; generated question ambiguity and semantic correctness remain unevaluated.
