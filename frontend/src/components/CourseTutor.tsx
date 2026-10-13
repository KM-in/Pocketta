import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import { EvidenceContext, EvidenceLinks } from "./EvidenceLinks";

export interface TutorEvidence {
  chunk_id: string; content_unit_id: string; source_id: string; source_name: string; source_version: number;
  citation?: { page_no?: number | null; slide_no?: number | null; start_sec?: number | null; end_sec?: number | null };
  location?: string;
}
export function citationHref(courseId: string, item: TutorEvidence) {
  return `/courses/${encodeURIComponent(courseId)}/sources/${encodeURIComponent(item.source_id)}?citation=${encodeURIComponent(item.content_unit_id)}&version=${item.source_version}`;
}
export function citationLabel(item: TutorEvidence) {
  const citation = item.citation;
  if (citation) {
    const seconds = citation.start_sec ?? 0;
    return `${item.source_name} · ${citation.page_no != null ? `page ${citation.page_no}` : citation.slide_no != null ? `slide ${citation.slide_no}` : `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`}`;
  }
  const location = item.location;
  if (location?.startsWith("page:") || location?.startsWith("slide:")) {
    return `${item.source_name} · ${location.replace(":", " ")}`;
  }
  if (location?.startsWith("time:")) {
    const milliseconds = Number(location.slice(5).split("-")[0]);
    if (Number.isFinite(milliseconds)) {
      const seconds = Math.floor(milliseconds / 1000);
      return `${item.source_name} · ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    }
  }
  return item.source_name;
}
interface Turn {
  id: string; question: string; status: string; claims: { text: string; chunk_ids: string[] }[];
  evidence: { items: TutorEvidence[]; warnings: string[] };
  check: { question: string; chunk_ids: string[] } | null;
  response: string | null;
  grade: { score: number; feedback: string; confidence: number; uncertain: boolean } | null;
}
const jsonPost = (body: unknown) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function CourseTutor({ courseId }: { courseId: string }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [intent, setIntent] = useState("explain");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    void request<Turn[]>(`/courses/${courseId}/tutor`).then(result => { if (!cancelled) setTurns(result); })
      .catch(cause => { if (!cancelled) setError(String(cause.message ?? cause)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [courseId]);
  async function ask() {
    setBusy(true); setError("");
    try {
      const turn = await request<Turn>(`/courses/${courseId}/tutor`, jsonPost({ question, intent }));
      setTurns(current => [...current, turn]); setQuestion("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Tutor unavailable"); }
    finally { setBusy(false); }
  }
  return <section className="setup-card tutor" aria-label="Course tutor">
    <Link to={`/courses/${courseId}`}>← Course sources</Link>
    <h2>Ask your course tutor</h2>
    <p>Answers use this course’s reliable source excerpts and pass a separate support check. Understanding checks are saved separately from ordinary conversation.</p>
    {loading && <p>Loading conversation…</p>}
    {error && <p role="alert">{error}</p>}
    <div aria-live="polite">{turns.map(turn => <TutorTurn key={turn.id} courseId={courseId} turn={turn} busy={busy} onAnswer={async response => {
      setBusy(true); setError("");
      try {
        const updated = await request<Turn>(`/courses/${courseId}/tutor/${turn.id}/answer`, jsonPost({ response }));
        setTurns(current => current.map(item => item.id === updated.id ? updated : item));
      } catch (cause) { setError(cause instanceof Error ? cause.message : "Grading unavailable"); }
      finally { setBusy(false); }
    }} />)}</div>
    <form onSubmit={event => { event.preventDefault(); void ask(); }}>
      <label>Teaching style<select aria-label="Teaching style" value={intent} onChange={event => setIntent(event.target.value)}>
        <option value="explain">Explain simply</option><option value="example">Give an example</option><option value="compare">Compare concepts</option><option value="check">Test my understanding</option>
      </select></label>
      <label>Course question<textarea aria-label="Course question" required maxLength={2000} value={question} onChange={event => setQuestion(event.target.value)} /></label>
      <button className="button" disabled={loading || busy || !question.trim()}>{busy ? "Checking course evidence…" : "Ask tutor"}</button>
    </form>
  </section>;
}

function TutorTurn({ courseId, turn, busy, onAnswer }: { courseId: string; turn: Turn; busy: boolean; onAnswer: (response: string) => Promise<void> }) {
  const [response, setResponse] = useState("");
  const evidence = Object.fromEntries(turn.evidence.items.map(item => [item.chunk_id, { label: citationLabel(item), target: item.content_unit_id, href: citationHref(courseId, item) }]));
  return <article className="content-card tutor-turn">
    <h3>You: {turn.question}</h3>
    <EvidenceContext.Provider value={evidence}>
      {turn.status === "unsupported" && <p>I could not verify an answer from this course’s reliable evidence. Try a more specific question or add relevant course material.</p>}
      {turn.claims.map((claim, index) => <div key={index}><p>{claim.text}</p><EvidenceLinks ids={claim.chunk_ids} /></div>)}
      {turn.check && <div className="understanding-check"><h4>Understanding check</h4><p>{turn.check.question}</p><EvidenceLinks ids={turn.check.chunk_ids} />
        {!turn.grade ? <form onSubmit={event => { event.preventDefault(); void onAnswer(response); }}>
          <label>Your answer<textarea aria-label={`Your answer to ${turn.check.question}`} maxLength={5000} required value={response} onChange={event => setResponse(event.target.value)} /></label>
          <button className="button secondary" disabled={busy || !response.trim()}>Submit understanding check</button>
        </form> : <div><p>Your answer: {turn.response}</p><p>{turn.grade.uncertain ? "Uncertain grade — review the evidence. " : ""}Score: {Math.round(turn.grade.score * 100)}% · Confidence: {Math.round(turn.grade.confidence * 100)}%</p><p>{turn.grade.feedback}</p></div>}
      </div>}
    </EvidenceContext.Provider>
    {turn.evidence.warnings.map(warning => <p className="editing-note" key={warning}>{warning}</p>)}
  </article>;
}
