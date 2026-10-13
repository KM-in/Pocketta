import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { QuizWorkspace } from "./QuizWorkspace";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const question = { id: "q1", kind: "mcq" as const, topic: "Concurrency", prompt: "Which answer is supported?", options: ["A", "B"], chunk_ids: ["ch"], citations: [{ chunk_id: "ch", content_unit_id: "unit", source_id: "s1", source_name: "Lecture", source_version: 1, location: "page:10" }] };
const quiz = { id: "quiz", title: "Mixed quiz", status: "ready", stale: false, pack_id: "pack", instructions: {}, questions: [question], attempts: [], warnings: [] };
const learning = { topics: [], known_topics: ["Concurrency"], syllabus_progress: { has_syllabus: false, material_available: 0, studied: 0, assessed: 0, mastered: 0, total: 0 }, syllabus_topics: [] };
const syllabus = { markdown: "", active: false, topics: [] };
const attempt = { id: "attempt", quiz_id: "quiz", status: "in_progress", answers: {}, grades: {}, questions: [question] };

it("keeps answer keys hidden during an attempt and reveals feedback after grading", async () => {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    let body: unknown = {};
    if (path.endsWith("/quizzes")) body = [quiz];
    else if (path.endsWith("/learning")) body = learning;
    else if (path.endsWith("/syllabus")) body = syllabus;
    else if (path.endsWith("/attempts")) body = attempt;
    else if (path.endsWith("/answers")) body = { ...attempt, answers: { q1: "A" } };
    else if (path.endsWith("/submit")) body = { ...attempt, status: "completed", answers: { q1: "A" }, grades: { q1: { score: 1, confidence: 1, uncertain: false, feedback: "Correct." } } };
    else if (path.endsWith("/quizzes/quiz")) body = { ...quiz, questions: [{ ...question, answer: "A", explanation: "Evidence says A." }], attempts: [{ id: "attempt", status: "completed", created_at: "now", score: 1 }] };
    else if (path.endsWith("/quiz-attempts/attempt")) body = { ...attempt, status: "completed", answers: { q1: "A" }, grades: { q1: { score: 1, confidence: 1, uncertain: false, feedback: "Correct." } } };
    return { ok: true, status: 200, json: async () => body };
  });
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter><QuizWorkspace courseId="course" sourceIds={["s1", "s2"]} sources={[{ id: "s1", name: "Lecture" }, { id: "s2", name: "Textbook" }]} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "Start / retake" }));
  expect(await screen.findByText("Which answer is supported?")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Lecture · page 10" })).toHaveAttribute("href", "/courses/course/sources/s1?citation=unit&version=1");
  expect(screen.queryByText("Evidence says A.")).toBeNull();
  fireEvent.click(screen.getByLabelText("A"));
  fireEvent.click(screen.getByRole("button", { name: "Submit quiz" }));
  expect(await screen.findByText("Evidence says A.")).toBeInTheDocument();
  expect(screen.getByText(/Score: 100%/)).toBeInTheDocument();
  await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/submit"), expect.objectContaining({ method: "POST" })));
});

it("separates the progress section and preserves backend learning observations", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, status: 200, json: async () => url.endsWith("/quizzes") ? [quiz] : url.endsWith("/syllabus") ? syllabus : { ...learning, topics: [{ topic_id: "topic", title: "Concurrency", average: .6, mastered: false, weak: true, observations: [{ uncertain: true, score: .4, response: "My answer", answer: "Expected answer", explanation: "Source explanation", feedback: "Review the evidence" }] }] } })));
  render(<MemoryRouter><QuizWorkspace courseId="course" sourceIds={[]} sources={[]} view="progress" /></MemoryRouter>);
  expect(await screen.findByText("Review recommended")).toBeInTheDocument();
  expect(screen.getByText(/60% average across recorded observations/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Start / retake" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Review 1 observations"));
  expect(screen.getByText("Uncertain grade — review the evidence")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download user_learning.md" })).toHaveAttribute("href", `${window.location.origin}/api/courses/course/learning/user_learning.md`);
});

it("autosaves answers and shows the saved status during a practice attempt", async () => {
  const fetch = vi.fn(async (url: string) => ({ ok: true, status: 200, json: async () => url.endsWith("/quizzes") ? [quiz] : url.endsWith("/learning") ? learning : url.endsWith("/syllabus") ? syllabus : attempt }));
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter><QuizWorkspace courseId="course" sourceIds={["s1"]} sources={[]} view="practice" /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "Start / retake" }));
  fireEvent.click(await screen.findByLabelText("A"));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/answers"), expect.objectContaining({ method: "PUT", body: JSON.stringify({ answers: { q1: "A" } }) })));
  expect(await screen.findByText("All answers saved")).toBeInTheDocument();
  expect(screen.getByLabelText("Quiz answers completed")).toHaveAttribute("value", "1");
  fireEvent.click(screen.getByRole("button", { name: "Back to quiz library" }));
  expect(await screen.findByRole("button", { name: "Start / retake" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Back to quiz library" })).not.toBeInTheDocument();
});
