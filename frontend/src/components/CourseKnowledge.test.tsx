import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { CourseKnowledge } from "./CourseKnowledge";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("searches the active course and shows exact evidence locations", async () => {
  const fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({
    items: [{ chunk_id: "chunk", content_unit_id: "unit", source_id: "slides", source_name: "Scheduling", source_version: 1, excerpt: "Round robin uses a time quantum.", citation: { slide_no: 7 } }], warnings: [], coverage: "supported", retrieval_mode: "hybrid",
  }) }));
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter><CourseKnowledge courseId="os" /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Search course material"), { target: { value: "round robin" } });
  fireEvent.click(screen.getByRole("button", { name: "Search sources" }));
  expect(await screen.findByText("Round robin uses a time quantum.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Scheduling · slide 7" })).toHaveAttribute("href", "/courses/os/sources/slides?citation=unit&version=1");
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/courses/os/retrieve"), expect.objectContaining({ method: "POST" }));
});

it("shows unsupported evidence and semantic fallback clearly", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ items: [], warnings: ["Semantic search unavailable"], coverage: "unsupported", retrieval_mode: "keyword" }) })));
  render(<MemoryRouter><CourseKnowledge courseId="os" /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Search course material"), { target: { value: "photosynthesis" } });
  fireEvent.click(screen.getByRole("button", { name: "Search sources" }));
  expect(await screen.findByText(/No reliable course evidence found/)).toBeInTheDocument();
  expect(screen.getByText("Semantic search unavailable")).toBeInTheDocument();
});
