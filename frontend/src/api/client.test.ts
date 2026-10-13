import { afterEach, describe, expect, it, vi } from "vitest";
import { uploadRequest, api, request } from "./client";

function fakeUpload() {
  const xhr = {
    open: vi.fn(), send: vi.fn(), status: 202, statusText: "Accepted", responseText: '{"id":"source"}',
    upload: { onprogress: null as null | ((event: ProgressEvent) => void), onload: null as null | (() => void) },
    onload: null as null | (() => void), onerror: null as null | (() => void), onabort: null as null | (() => void),
  };
  vi.stubGlobal("XMLHttpRequest", function () { return xhr; });
  return xhr;
}
afterEach(() => vi.unstubAllGlobals());

describe("upload transport", () => {
  it("reports measured and indeterminate progress and waits for server acceptance", async () => {
    const xhr = fakeUpload();
    const progress = vi.fn();
    const body = new FormData();
    const pending = uploadRequest("/courses/a/sources", body, progress);
    xhr.upload.onprogress?.(new ProgressEvent("progress", { loaded: 25, total: 100, lengthComputable: true }));
    expect(progress).toHaveBeenLastCalledWith({ loaded: 25, total: 100, transferred: false });
    xhr.upload.onprogress?.(new ProgressEvent("progress", { loaded: 50 }));
    expect(progress).toHaveBeenLastCalledWith({ loaded: 50, total: null, transferred: false });
    xhr.upload.onload?.();
    expect(progress).toHaveBeenLastCalledWith({ loaded: 0, total: null, transferred: true });
    xhr.onload?.();
    expect(await pending).toEqual({ id: "source" });
    expect(xhr.send).toHaveBeenCalledWith(body);
  });
  it("preserves server rejection details", async () => {
    const xhr = fakeUpload();
    const pending = uploadRequest("/lectures", new FormData());
    xhr.status = 413; xhr.responseText = '{"detail":"Upload exceeds configured limit"}';
    xhr.onload?.();
    await expect(pending).rejects.toThrow("Upload exceeds configured limit");
  });
  it("reports network and malformed response failures", async () => {
    const xhr = fakeUpload();
    const pending = uploadRequest("/lectures", new FormData());
    xhr.onerror?.();
    await expect(pending).rejects.toThrow("Upload connection failed");
    const bad = uploadRequest("/lectures", new FormData());
    xhr.responseText = "not JSON"; xhr.onload?.();
    await expect(bad).rejects.toThrow("202");
  });
  it("uses the same upload transport for legacy recordings", async () => {
    const xhr = fakeUpload();
    const progress = vi.fn();
    const pending = api.upload(new File(["audio"], "recording.webm"), "Lecture", progress);
    expect(xhr.open).toHaveBeenCalledWith("POST", expect.stringContaining("/lectures"));
    const body = xhr.send.mock.calls[0][0] as FormData;
    expect(body.get("title")).toBe("Lecture");
    xhr.onload?.();
    await pending;
  });
});

describe("API connection failures", () => {
  it("explains browser network failures and preserves their cause", async () => {
    const cause = new TypeError("Load failed");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(cause));
    const failure = await request("/courses").catch(error => error);
    expect(failure).toBeInstanceOf(Error);
    if (!(failure instanceof Error)) throw new Error("Expected a connection error");
    expect(failure.message).toContain("Cannot connect to the PocketTA backend");
    expect(failure.cause).toBe(cause);
  });
  it("uses the frontend origin for default API requests", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    vi.stubGlobal("fetch", fetch);
    await request("/courses");
    expect(fetch).toHaveBeenCalledWith(`${window.location.origin}/api/courses`, undefined);
  });
});
