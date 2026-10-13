import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CourseWorkspace from "./CourseWorkspace";

const courses = [{ id: "a", title: "Operating systems", description: "Study processes", source_count: 1 }, { id: "b", title: "Networks", description: "", source_count: 0 }];
const source = { id: "s", course_id: "a", name: "Chapter one", type: "pdf", version: 1, status: "ready", progress: 100, error: null, asset_url: "/sources/s/asset", content_units: [{ id: "unit", location: "page:2", text: "Process evidence", native_text: "Process evidence", uncertain: false, preview_url: "/sources/s/units/unit/image" }], study_pack: { title: "Revision", overview: "Summary", notes: [{ title: "Processes", body: "A process runs code", content_unit_ids: ["unit"] }], concepts: [], flashcards: [], quiz: [] } };
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  window.history.replaceState({}, "", "/");
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname.replace("/api", "");
    let data: unknown;
    if (path === "/courses" && init?.method === "POST") data = { id: "new", ...JSON.parse(init.body as string) };
    else if (path === "/courses") data = courses;
    else if (path === "/health") data = { ready: false, components: { cerebras: { ready: false, detail: "Missing key", remediation: "Configure key" } } };
    else if (path.endsWith("/study-packs")) data = [];
    else if (path === "/courses/a/sources") data = [source];
    else if (path === "/courses/b/sources" || path === "/courses/new/sources") data = [];
    else if (path === "/courses/a/citations/unit") data = { content_unit_id: "unit", source_id: "s", source_name: "Chapter one", page_no: 2 };
    else if (path === "/sources/s") data = source;
    else throw new Error(`Unexpected request ${path}`);
    return { ok: true, status: 200, json: async () => data };
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("Course workspace", () => {
  it("limits batch uploads to two concurrent transfers and keeps the course route", async () => {
    window.history.replaceState({}, "", "/courses/a");
    const transfers: Array<{ status: number; responseText: string; upload: Record<string, unknown>; onload: null | (() => void); open: ReturnType<typeof vi.fn>; send: ReturnType<typeof vi.fn> }> = [];
    vi.stubGlobal("XMLHttpRequest", vi.fn(function () {
      const transfer = { status: 202, responseText: JSON.stringify(source), upload: {}, onload: null as null | (() => void), open: vi.fn(), send: vi.fn() };
      transfers.push(transfer);
      return transfer;
    }));
    render(<CourseWorkspace />);
    const input = await screen.findByLabelText("Upload course source");
    fireEvent.change(input, { target: { files: [new File(["a"], "a.pdf"), new File(["b"], "b.pdf"), new File(["c"], "c.pdf")] } });
    await waitFor(() => expect(transfers).toHaveLength(2));
    await act(async () => { transfers[0].onload?.(); });
    await waitFor(() => expect(transfers).toHaveLength(3));
    await act(async () => { transfers[1].onload?.(); transfers[2].onload?.(); });
    expect(window.location.pathname).toBe("/courses/a");
  });
  it("allows creating a course without engine readiness", async () => {
    render(<CourseWorkspace />);
    await screen.findByText("Operating systems");
    fireEvent.click(screen.getByRole("button", { name: /New course/ }));
    fireEvent.change(screen.getByLabelText("Course title"), { target: { value: "Algorithms" } });
    fireEvent.click(screen.getByRole("button", { name: "Save course" }));
    await waitFor(() => expect(window.location.pathname).toBe("/courses/new"));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/courses"), expect.objectContaining({ method: "POST" }));
  });
  it("restores a source route and resolves citations to its page", async () => {
    window.history.replaceState({}, "", "/courses/a/sources/s");
    render(<CourseWorkspace />);
    const citation = await screen.findByRole("link", { name: "Chapter one · page 2" });
    const unit = document.getElementById("unit")!;
    unit.scrollIntoView = vi.fn();
    fireEvent.click(citation);
    await waitFor(() => expect(unit.scrollIntoView).toHaveBeenCalled());
    expect(await screen.findByTitle("Cited page 2")).toHaveAttribute("src", expect.stringContaining("#page=2"));
    expect(screen.getByAltText("Original page 2")).toHaveAttribute("loading", "lazy");
    expect(screen.getByText(/selected page images are sent to the configured cloud provider/)).toBeInTheDocument();
  });
  it("clears the source view when switching courses", async () => {
    window.history.replaceState({}, "", "/courses/a/sources/s");
    render(<CourseWorkspace />);
    await screen.findByRole("heading", { name: "Chapter one" });
    fireEvent.click(screen.getByRole("link", { name: /Networks/ }));
    await screen.findByText("No material yet. Upload a source or record a lecture.");
    expect(screen.queryByText("Process evidence")).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/courses/b");
  });
  it("rejects a source route pointing at another course", async () => {
    window.history.replaceState({}, "", "/courses/b/sources/s");
    render(<CourseWorkspace />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Source does not belong to this course");
    expect(screen.queryByText("Process evidence")).not.toBeInTheDocument();
  });
  it("shows transfer progress independently of processing", async () => {
    window.history.replaceState({}, "", "/courses/a");
    const xhr = {
      open: vi.fn(), send: vi.fn(), status: 202, responseText: JSON.stringify(source),
      upload: { onprogress: null as null | ((event: ProgressEvent) => void), onload: null as null | (() => void) },
      onload: null as null | (() => void),
    };
    vi.stubGlobal("XMLHttpRequest", function () { return xhr; });
    render(<CourseWorkspace />);
    const input = await screen.findByLabelText("Upload course source");
    fireEvent.change(input, { target: { files: [new File(["pdf"], "chapter.pdf")] } });
    expect(await screen.findByText("Uploading…")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Upload progress" })).not.toHaveAttribute("value");
    act(() => xhr.upload.onprogress?.(new ProgressEvent("progress", { loaded: 40, total: 100, lengthComputable: true })));
    expect(screen.getByText("Uploading · 40%")).toBeInTheDocument();
    act(() => xhr.upload.onload?.());
    expect(screen.getByText("Upload complete; waiting for server")).toBeInTheDocument();
    await act(async () => xhr.onload?.());
    await waitFor(() => expect(window.location.pathname).toBe("/courses/a/sources/s"));
    expect(screen.queryByLabelText("Upload transfer")).not.toBeInTheDocument();
  });
  it("ignores upload callbacks after switching courses", async () => {
    window.history.replaceState({}, "", "/courses/a");
    const xhr = {
      open: vi.fn(), send: vi.fn(), status: 202, responseText: JSON.stringify(source),
      upload: { onprogress: null as null | ((event: ProgressEvent) => void) },
      onload: null as null | (() => void),
    };
    vi.stubGlobal("XMLHttpRequest", function () { return xhr; });
    render(<CourseWorkspace />);
    fireEvent.change(await screen.findByLabelText("Upload course source"), { target: { files: [new File(["pdf"], "chapter.pdf")] } });
    await screen.findByText("Uploading…");
    fireEvent.click(screen.getByRole("link", { name: /Networks/ }));
    await screen.findByText("No material yet. Upload a source or record a lecture.");
    act(() => xhr.upload.onprogress?.(new ProgressEvent("progress", { loaded: 40, total: 100, lengthComputable: true })));
    await act(async () => xhr.onload?.());
    expect(window.location.pathname).toBe("/courses/b");
    expect(screen.queryByLabelText("Upload transfer")).not.toBeInTheDocument();
  });

});
