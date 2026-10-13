import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { CitationFocus } from "./CitationFocus";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function show(recording = true) {
  return render(<MemoryRouter initialEntries={["/courses/os/sources/source?citation=unit&version=2"]}><CitationFocus courseId="os" sourceId="source" assetUrl="/sources/source/asset" recording={recording} /></MemoryRouter>);
}
it("resolves a course citation and seeks a recording to its exact fractional timestamp", async () => {
  const fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ content_unit_id: "unit", target_id: "seg-4", source_id: "source", source_name: "Lecture", start_sec: 62.125, end_sec: 79 }) }));
  vi.stubGlobal("fetch", fetch);
  const { container } = show();
  await screen.findByText("Cited recording · 62.125s–79s");
  const video = container.querySelector("video")!;
  fireEvent.loadedMetadata(video);
  expect(video.currentTime).toBe(62.125);
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/courses/os/citations/unit?version=2"), undefined);
});
it("opens a cited slide at the matching converted PDF page", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ content_unit_id: "unit", source_id: "source", source_name: "Slides", slide_no: 7 }) })));
  show(false);
  expect(await screen.findByTitle("Cited page 7")).toHaveAttribute("src", expect.stringContaining("#page=7"));
});
it("does not load playback when a saved citation is stale", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 409, json: async () => ({ detail: "Source changed since this citation was saved" }) })));
  const { container } = show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Source changed");
  expect(container.querySelector("video")).toBeNull();
});
it("rejects a citation pointing to another source", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ source_id: "foreign" }) })));
  const { container } = show(false);
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("does not belong"));
  expect(container.querySelector("iframe")).toBeNull();
});

it("uses a rendered slide image when a unit preview is available", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ content_unit_id: "unit", source_id: "source", source_name: "Slides", slide_no: 7 }) })));
  render(<MemoryRouter initialEntries={["/courses/os/sources/source?citation=unit"]}><CitationFocus courseId="os" sourceId="source" assetUrl="/sources/source/asset" recording={false} previews={{ unit: "/sources/source/units/unit/image" }} /></MemoryRouter>);
  expect(await screen.findByAltText("Cited slide 7")).toHaveAttribute("src", expect.stringContaining("/units/unit/image"));
});
