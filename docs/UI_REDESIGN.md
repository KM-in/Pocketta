# PocketTA UI redesign from current main

## Branch and scope

The old `codex/pocketta-ui-redesign` branch was deleted locally and from GitHub as requested. `main` was pulled with `git pull --ff-only origin main`, advancing to `c08bead`. The new branch, `codex/pocketta-workspace-redesign`, was created directly from that commit.

The agreed visual direction remains **calm, intelligent, source-grounded learning**. This implementation incorporates the current mainline's multi-source packs, immutable quiz library, saved attempts, learning observations, and syllabus mapping. It does not replace them with the earlier branch's simpler capabilities.

Pre-existing backend/provider edits were preserved in the named Git stash `Preserve pre-existing backend edits before fresh UI branch`. They remain separate because main has newer provider configuration and tests. This redesign changes frontend files and documentation only. Existing local data and generated output were preserved.

## Interface and workflow

- **My courses:** course grid, real source counts, descriptions, loading/error recovery, native course dialog, and first-course onboarding only after a successful empty response.
- **Shared shell:** 240px sidebar, optional compact sidebar, breadcrumbs, local runtime status, source-aware course navigation, mobile modal drawer, keyboard skip link, and saved light/dark theme.
- **Overview and sources:** actual processing counts, quick actions, multi-file upload with the existing two-transfer concurrency, microphone/browser recording, source selection, separate source-opening links, batch indexing, and selected-source search.
- **Study packs:** current multi-source generation, real job stages/progress, retry/cancel, stale warnings, verified notes and concepts, animated question/answer flip cards, coverage gaps, original evidence, and links into the actual mixed quiz library.
- **Practice:** the existing custom quiz builder with question count/mix, difficulty, topic constraints, and instructions; immutable quiz library, resume/retake/review, answer autosave feedback, focused answering mode, source citations, short answers, grading progress, and real saved results. Leaving an attempt saves answers before returning to the library.
- **Learning progress:** actual syllabus dimensions, topic observations, averages, backend mastery/weak-topic flags, uncertainty, feedback, and the learning report download. No invented completion values or inferred UI-side mastery rules.
- **Syllabus:** Markdown input/upload, proposed source mappings, confirmation, studied markers, evidence links, and download.
- **Tutor:** restored conversation, teaching-style selection, saved understanding checks, source panel on desktop, inline citations on mobile, warnings, and question composer.
- **Source viewer:** document previews and extracted text, original-media playback and exact timestamp seeking, transcript correction, existing retry/cancel/export/delete, rendered-slide previews with converted-PDF fallback, and persistent citation highlighting.
- **Runtime:** existing readiness and remediation information with provider/privacy disclosure. Configuration remains server-managed and credentials are not displayed.

Student flow: open/create a course → upload sources → select relevant material → generate a connected study pack or custom quiz → study/practice → ask the tutor → follow evidence → review saved learning observations and syllabus progress.

## Implementation

React, Vite, TypeScript, React Router, and plain CSS remain in place. No dependencies were added. `WorkspaceUI.tsx` contains the shared shell, page header, dialog, empty state, and one local SVG icon family. Existing `CoursePacks` and `QuizWorkspace` retain their API contracts while gaining the shared styling and separate practice/progress presentations.

Semantic CSS tokens cover backgrounds, surfaces, text, borders, indigo actions, semantic statuses, focus, radius, shadows, and a 4px spacing scale. Typography uses an offline-compatible Avenir/Segoe UI stack. Ordinary surfaces use thin borders and restrained elevation. Reading layouts are narrower than dashboards. Motion is subtle and reduced-motion preferences are honored.

The default API base uses the browser's own `/api` origin; Vite dev/preview proxies to `127.0.0.1:8000`. This retains the connection fix when Vite selects a fallback port. `VITE_API_BASE_URL` overrides remain available. Backend CORS was not broadened.

Existing course, tutor, and source URLs and citation/version parameters remain valid. New section routes are `/courses/:courseId/sources`, `/packs`, `/practice`, and `/progress`. A mixed pack quiz links to `/practice#quiz-<id>`; the actual library row receives focus after loading. Source selection survives navigation between course sections.

## Skills

- `frontend-design`: the requested primary skill, read again for this branch; visual hierarchy, spacing, typography, neutral/indigo identity, and deliberate application composition.
- `react-components`: typed component boundaries, effect cleanup, state ownership, and routing.
- `frontend-accessibility`: native dialogs, keyboard tabs and navigation, source-checkbox labels, text-based answer/status feedback, visible focus, responsive controls, and reduced motion.

No applicable project `AGENTS.md`, dedicated Playwright skill, or `web-design-guidelines` skill was found. Browser verification uses the locally installed Playwright library and Chromium directly. No runtime remote fonts or decorative assets are used.

## Verification and limitations

- Frontend tests: **46 passed across 12 files**. Includes current-main pack/quiz/batch-upload tests plus regression checks for source selection across sections, autosave, separated progress, network retry, theme/dialog behavior, pack tabs, and citation previews.
- Strict TypeScript compilation and Vite production build: **passed**.
- `git diff --check`: **passed**.
- No configured lint script is available. Backend code was not changed; backend tests were not run as part of this frontend task.
- Browser matrix: **14 scenarios × 4 widths × 2 themes = 112 screenshots**, at 360, 768, 1024, and 1440px in light/dark themes. Scenarios include dashboard, overview, sources, expanded multi-source pack, practice library, custom quiz form, active quiz, graded results, progress/syllabus, tutor, source reader, citation, empty dashboard, and processing.
- The browser harness intercepts only root `/api/` requests with isolated development fixtures; no synthetic data is written to the application or real database. It also checks selection across sections, mobile navigation/Escape, quiz autosave/results, and citation focus.
- Results and screenshots are generated locally under `output/ui-redesign-main/`, separate from the previous branch's screenshots. `verify.cjs` accepts optional `PLAYWRIGHT_MODULE` and `CHROMIUM_PATH` environment paths.
- Live AI generation, provider availability, native transcription, device capture permissions, and native PDF rendering were not exercised by the fixture matrix. A full screen-reader/zoom/automated WCAG audit was not performed, so no full conformance claim is made.
- Source-level practice quizzes remain an immediate-feedback utility; durable attempts and learning history are provided by the current course quiz API.

Restart the backend after changing from the old branch so its running process loads the new mainline's pack, quiz, learning, and syllabus routes. Restart the frontend if needed and open the URL printed by Vite.

## Flashcard interaction

Source-level and course-wide flashcards use the shared `Flashcard.tsx` component. The question appears on the front; clicking or pressing Enter/Space flips to the answer and back. CSS provides a reversible 420ms 3D rotation, with no transition under reduced-motion preferences. Both faces size the card so longer answers stay readable. Citations remain outside the toggle and print output includes both question and answer.

Browser checks passed for both pack types at 360px and 1440px in both themes: click, keyboard activation, repeated toggles, reduced motion, retained citations, and no horizontal overflow. Results are in `output/ui-redesign-main/flashcard-verification.json`.
