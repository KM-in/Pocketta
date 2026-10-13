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
