import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { CourseTutor } from "./CourseTutor";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const item = { chunk_id: "chunk", content_unit_id: "unit", source_id: "book", source_name: "OS textbook", source_version: 2, citation: { page_no: 44 } };
const turn = { id: "turn", question: "Explain deadlock", status: "answered", claims: [{ text: "Processes wait forever for resources.", chunk_ids: ["chunk"] }], evidence: { items: [item], warnings: [] }, check: null, grade: null, response: null };
const show = () => render(<MemoryRouter><CourseTutor courseId="os" /></MemoryRouter>);
it("restores saved cited conversation and posts the selected teaching intent", async () => {
  const fetch = vi.fn(async (_url, options) => ({ ok: true, status: 200, json: async () => options?.method ? { ...turn, id: "new", question: "Compare processes" } : [turn] }));
  vi.stubGlobal("fetch", fetch); show();
  await screen.findByText("Processes wait forever for resources.");
  expect(screen.getByRole("link", { name: "OS textbook · page 44" })).toHaveAttribute("href", "/courses/os/sources/book?citation=unit&version=2");
  fireEvent.change(screen.getByLabelText("Teaching style"), { target: { value: "compare" } });
  fireEvent.change(screen.getByLabelText("Course question"), { target: { value: "Compare processes" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask tutor" }));
  await screen.findByText("You: Compare processes");
  expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining("/courses/os/tutor"), expect.objectContaining({ body: JSON.stringify({ question: "Compare processes", intent: "compare" }) }));
});
it("submits only an explicit understanding check and restores its uncertain grade", async () => {
  const check = { ...turn, claims: [], check: { question: "Name two conditions", chunk_ids: ["chunk"] } };
  const fetch = vi.fn(async (_url, options) => ({ ok: true, status: 200, json: async () => options?.method ? { ...check, response: "mutual exclusion", grade: { score: 0.5, confidence: 0.6, uncertain: true, feedback: "Review the evidence." } } : [check] }));
  vi.stubGlobal("fetch", fetch); show();
  fireEvent.change(await screen.findByLabelText("Your answer to Name two conditions"), { target: { value: "mutual exclusion" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit understanding check" }));
  expect(await screen.findByText(/Uncertain grade/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Submit understanding check" })).toBeNull();
  expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining("/courses/os/tutor/turn/answer"), expect.objectContaining({ method: "POST" }));
});
it("shows refusal without unsupported claims", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => [{ ...turn, status: "unsupported", claims: [], evidence: { items: [], warnings: [] } }] })));
  show();
  expect(await screen.findByText(/could not verify an answer/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Submit understanding check" })).toBeNull();
});
