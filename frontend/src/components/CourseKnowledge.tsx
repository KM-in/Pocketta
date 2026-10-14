import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { citationHref } from "./CourseTutor";
import { request } from "../api/client";

interface Evidence {
  chunk_id: string; content_unit_id: string; source_id: string; source_name: string;
  source_version: number; excerpt: string;
  visual_url?: string | null;
  citation: { page_no?: number | null; slide_no?: number | null; start_sec?: number | null; end_sec?: number | null };
}
interface Bundle { items: Evidence[]; coverage: string; retrieval_mode: string; warnings: string[] }
interface CourseTopic { id: string; name: string; level: string; parent_topic_id?: string | null; parent_name?: string | null }
interface TopicGraph { topics: CourseTopic[]; prerequisites: { topic_id: string; prerequisite_topic_id: string }[] }

function label(item: Evidence) {
  const c = item.citation;
  if (c.page_no != null) return `page ${c.page_no}`;
  if (c.slide_no != null) return `slide ${c.slide_no}`;
  const stamp = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
  return `${stamp(c.start_sec ?? 0)}–${stamp(c.end_sec ?? 0)}`;
}

export function CourseKnowledge({ courseId, sourceIds = [], refreshVersion = 0, indexState = "" }: { courseId: string; sourceIds?: string[]; refreshVersion?: number; indexState?: string }) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<Bundle | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const requestRevision = useRef(0);
  const [topicGraph, setTopicGraph] = useState<TopicGraph | null>(null);
  useEffect(() => {
    let cancelled = false;
    setTopicGraph(null);
    void request<TopicGraph>(`/courses/${courseId}/topics`)
      .then(value => {
        // Keep the panel resilient to older API responses and partial test/dev mocks.
        if (!cancelled) setTopicGraph(Array.isArray(value?.topics) ? value : null);
      })
      .catch(() => { if (!cancelled) setTopicGraph(null); });
    return () => { cancelled = true; };
  }, [courseId, refreshVersion, indexState]);
  return <section className="setup-card" aria-label="Course knowledge search">
    <h2>Search course material</h2>
    <p>Find source excerpts across this course’s PDFs, slides, and lectures. {sourceIds.length ? `Searching ${sourceIds.length} selected sources.` : "Searching all course sources."}</p>
    {topicGraph && topicGraph.topics.length > 0 && <details className="content-card course-topic-map">
      <summary>Course topics and concepts · {topicGraph.topics.length}</summary>
      <p>Topics are inferred from indexed source excerpts. Use source search to review supporting material.</p>
      {(["major_topic", "subtopic", "concept", "topic"] as const).map(level => {
        const topics = topicGraph.topics.filter(topic => (topic.level || "topic") === level);
        return topics.length > 0 && <section key={level} aria-label={level.replaceAll("_", " ")}>
          <h3>{level === "major_topic" ? "Major topics" : level === "subtopic" ? "Subtopics" : level === "concept" ? "Key concepts" : "Other indexed topics"}</h3>
          <ul>{topics.map(topic => <li key={topic.id}>{topic.name}{topic.parent_name && <span className="muted"> · under {topic.parent_name}</span>}</li>)}</ul>
        </section>;
      })}
      {Array.isArray(topicGraph.prerequisites) && topicGraph.prerequisites.length > 0 && <p>{topicGraph.prerequisites.length} prerequisite relationships inferred from course excerpts.</p>}
    </details>}
    <form onSubmit={event => {
      event.preventDefault();
      const current = ++requestRevision.current;
      setBusy(true); setError(""); setResult(null);
      void request<Bundle>(`/courses/${courseId}/retrieve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, limit: 6, ...(sourceIds.length ? { source_ids: sourceIds } : {}) }) })
        .then(bundle => { if (requestRevision.current === current) setResult(bundle); })
        .catch(cause => { if (requestRevision.current === current) setError(cause instanceof Error ? cause.message : "Search failed"); })
        .finally(() => { if (requestRevision.current === current) setBusy(false); });
    }}>
      <label>Search query<input aria-label="Search course material" value={query} maxLength={2000} onChange={event => setQuery(event.target.value)} /></label>
      <button className="button" disabled={busy || !query.trim()}>{busy ? "Searching…" : "Search sources"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result && <div aria-live="polite">
      {!result.items.length && <p>No reliable course evidence found. Try a different query or index your sources.</p>}
      {result.warnings.map(warning => <p key={warning} className="editing-note">{warning}</p>)}
      {result.items.map(item => <article className="content-card" key={item.chunk_id}>
        <Link to={citationHref(courseId, item)}>{item.source_name} · {label(item)}</Link>
        <p className="extracted-text">{item.excerpt}</p>
        {item.visual_url && <img className="course-evidence-image" src={`${import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api"}${item.visual_url}`} alt={`Visual evidence from ${item.source_name} at ${label(item)}`} loading="lazy" />}
      </article>)}
    </div>}
  </section>;
}
