import type { HealthResponse, LectureDetail, LectureSummary, SegmentCorrection } from "../types";

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
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

export const api = {
  health: () => request<HealthResponse>("/health"),
  list: () => request<LectureSummary[]>("/lectures"),
  get: (id: string) => request<LectureDetail>(`/lectures/${id}`),
  upload: (file: File, title?: string) => {
    const body = new FormData();
    body.append("file", file);
    if (title?.trim()) body.append("title", title.trim());
    return request<LectureSummary>("/lectures", { method: "POST", body });
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
