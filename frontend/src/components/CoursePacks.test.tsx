import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { CoursePacks } from "./CoursePacks";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const pack = {
  id: "p", title: "Course revision", overview: "Overview", status: "completed", progress: 100, error: null, warnings: [],
  source_snapshots: [{ id: "s", name: "Lecture" }, { id: "t", name: "Textbook" }],
  coverage: { cited_sources: ["s"], omitted_sources: [{ source_id: "t", name: "Textbook", reason: "No verified evidence" }] },
  sections: [{ key: "0", title: "Concurrency", status: "validated", reason: null, content: { items: [{ kind: "flashcard", title: "What is a mutex?", text: "Mutual exclusion", chunk_ids: ["ch"], options: [], correct_answer: null }] }, evidence: [{ chunk_id: "ch", content_unit_id: "unit", source_id: "s", source_name: "Lecture", source_version: 1, citation: { start_sec: 5 } }] }],
};
it("generates a pack for selected sources and displays topic citations and coverage", async () => {
  const fetch = vi.fn(async (_url: string, init?: RequestInit) => ({ ok: true, status: 200, json: async () => init?.method === "POST" ? pack : [pack] }));
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter><CoursePacks courseId="course" sourceIds={["s", "t"]} revision={0} /></MemoryRouter>);
  await screen.findByText("Concurrency");
  expect(screen.getByRole("link", { name: "Lecture · 0:05" })).toHaveAttribute("href", expect.stringContaining("citation=unit&version=1"));
  expect(screen.getByText("1 of 2 selected sources cited.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Generate course study pack" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/study-packs"), expect.objectContaining({ method: "POST", body: JSON.stringify({ source_ids: ["s", "t"] }) })));
});
it("disables generation without a selection and explains stale packs", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => [{ ...pack, status: "stale" }] })));
  render(<MemoryRouter><CoursePacks courseId="course" sourceIds={[]} revision={0} /></MemoryRouter>);
  expect(screen.getByRole("button", { name: "Generate course study pack" })).toBeDisabled();
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Source material changed"));
});
it("offers cancellation and progress for running packs", async () => {
  const fetch = vi.fn(async (_url: string, init?: RequestInit) => ({ ok: true, status: 200, json: async () => init?.method === "POST" ? pack : [{ ...pack, status: "generating", progress: 40 }] }));
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter><CoursePacks courseId="course" sourceIds={["s"]} revision={0} /></MemoryRouter>);
  expect(await screen.findByLabelText("Course pack progress")).toHaveAttribute("value", "40");
  fireEvent.click(screen.getByRole("button", { name: "Cancel pack" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/p/cancel"), expect.objectContaining({ method: "POST" })));
});
