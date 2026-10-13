import type { HealthResponse, LectureDetail, LectureSummary, SegmentCorrection } from "../types";

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? `${window.location.origin}/api`;

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch (cause) {
    if (cause instanceof TypeError) {
      throw new Error("Cannot connect to the PocketTA backend. Check that it is running at http://127.0.0.1:8000, then retry.", { cause });
    }
    throw cause;
  }
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail ?? message;
    } catch {
      // Preserve the HTTP status when the response is not JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export interface UploadProgress { loaded: number; total: number | null; transferred: boolean }

export function uploadRequest<T>(path: string, body: FormData, onProgress?: (progress: UploadProgress) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);
    xhr.upload.onprogress = event => onProgress?.({ loaded: event.loaded, total: event.lengthComputable ? event.total : null, transferred: false });
    xhr.upload.onload = () => onProgress?.({ loaded: 0, total: null, transferred: true });
    xhr.onerror = () => reject(new Error("Upload connection failed. Please retry."));
    xhr.onabort = () => reject(new Error("Upload cancelled."));
    xhr.onload = () => {
      let data: unknown;
      try { data = JSON.parse(xhr.responseText); }
      catch { reject(new Error(`${xhr.status} ${xhr.statusText || "Invalid server response"}`)); return; }
      if (xhr.status < 200 || xhr.status >= 300) {
        const detail = (data as { detail?: unknown })?.detail;
        reject(new Error(typeof detail === "string" ? detail : `${xhr.status} ${xhr.statusText}`));
      } else resolve(data as T);
    };
    xhr.send(body);
  });
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  list: () => request<LectureSummary[]>("/lectures"),
  get: (id: string) => request<LectureDetail>(`/lectures/${id}`),
  upload: (file: File, title?: string, onProgress?: (progress: UploadProgress) => void) => {
    const body = new FormData();
    body.append("file", file);
    if (title?.trim()) body.append("title", title.trim());
    return uploadRequest<LectureSummary>("/lectures", body, onProgress);
  },
  demo: (courseId?: string) => request<LectureSummary>(`/lectures/demo${courseId ? `?course_id=${courseId}` : ""}`, { method: "POST" }),
  update: (id: string, update: { title?: string; corrections?: SegmentCorrection[] }) =>
    request<LectureDetail>(`/lectures/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    }),
  generate: (id: string) => request<LectureSummary>(`/lectures/${id}/generate`, { method: "POST" }),
  cancel: (id: string) => request<LectureSummary>(`/lectures/${id}/cancel`, { method: "POST" }),
  delete: (id: string) => request<void>(`/lectures/${id}`, { method: "DELETE" }),
  exportUrl: (id: string) => `${API_BASE}/lectures/${id}/export.md`,
};
