import { useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { API_BASE, request } from "../api/client";
interface Citation {
  source_id: string; content_unit_id: string; source_name: string;
  target_id?: string; page_no?: number; slide_no?: number; start_sec?: number; end_sec?: number;
}

export function CitationFocus({ courseId, sourceId, assetUrl, recording }: { courseId: string; sourceId: string; assetUrl: string; recording: boolean }) {
  const [params] = useSearchParams();
  const navigationKey = useLocation().key;
  const unit = params.get("citation");
  const version = params.get("version");
  const [citation, setCitation] = useState<Citation | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    setCitation(null); setError("");
    if (unit) void request<Citation>(`/courses/${encodeURIComponent(courseId)}/citations/${encodeURIComponent(unit)}${version ? `?version=${encodeURIComponent(version)}` : ""}`)
      .then(result => {
        if (cancelled) return;
        if (result.source_id !== sourceId) { setError("Citation does not belong to this source"); return; }
        setCitation(result);
        // The transcript uses legacy segment IDs. Documents use content-unit IDs.
        const element = document.getElementById(unit) ?? document.getElementById(result.target_id ?? "");
        element?.scrollIntoView?.({ behavior: "smooth", block: "center" });
        if (element instanceof HTMLElement) element.focus();
      }).catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Citation unavailable"); });
    return () => { cancelled = true; };
  }, [courseId, sourceId, unit, version, navigationKey]);
  const mediaUrl = API_BASE + assetUrl;
  if (error) return <p role="alert">{error}</p>;
  if (recording) return <section className="setup-card" aria-label="Source playback">
    <h3>{citation ? `Cited recording · ${citation.start_sec}s–${citation.end_sec}s` : "Recording playback"}</h3>
    {(!unit || citation) && <video key={`${sourceId}-${unit}-${version}`} controls preload="metadata" src={mediaUrl} style={{ width: "100%", maxHeight: 360 }}
      onLoadedMetadata={event => { if (citation?.start_sec != null) event.currentTarget.currentTime = citation.start_sec; }} />}
  </section>;
  if (!citation) return unit ? <p>Opening cited source…</p> : null;
  const page = citation.page_no ?? citation.slide_no;
  return <section className="setup-card" aria-label="Cited document page">
    <h3>{citation.source_name} · {citation.slide_no != null ? "slide" : "page"} {page}</h3>
    <a href={`${mediaUrl}#page=${page}`} target="_blank" rel="noreferrer">Open cited page in a new tab</a>
    <iframe key={`${unit}-${version}`} title={`Cited page ${page}`} src={`${mediaUrl}#page=${page}`} style={{ width: "100%", height: 560, border: 0 }} />
  </section>;
}
