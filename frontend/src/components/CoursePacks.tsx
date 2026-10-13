import { useEffect, useState } from "react";
import { Flashcard } from "./Flashcard";
import { EmptyState, Icon } from "./WorkspaceUI";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import { citationHref, citationLabel, type TutorEvidence } from "./CourseTutor";

interface Item { kind: string; title: string; text: string; chunk_ids: string[]; options: string[]; correct_answer: number | null }
interface Section { key: string; title: string; status: string; reason: string | null; content: { items: Item[] }; evidence: TutorEvidence[] }
interface Pack {
  id: string; title: string; overview: string; status: string; progress: number; error: string | null;
  quiz_id?: string | null; quiz_status?: string | null;
  warnings: string[]; sections: Section[]; source_snapshots: { id: string; name: string }[];
  overview_evidence?: TutorEvidence[];
  coverage: { selected_sources?: string[]; cited_sources?: string[]; omitted_sources?: { source_id: string; name: string; reason: string }[] };
}
const active = new Set(["queued", "indexing", "planning", "generating", "assembling"]);
const post = (body?: unknown) => ({ method: "POST", headers: { "Content-Type": "application/json" }, ...(body ? { body: JSON.stringify(body) } : {}) });

export function CoursePacks({ courseId, sourceIds, revision }: { courseId: string; sourceIds: string[]; revision: number }) {
  const [loading, setLoading] = useState(true);
  const [packs, setPacks] = useState<Pack[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const result = await request<Pack[]>(`/courses/${courseId}/study-packs`);
        if (cancelled) return;
        setPacks(result);
        if (result.some(p => active.has(p.status))) timer = setTimeout(() => void load(), 1500);
      } catch (cause) { if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load course packs"); }
      finally { if (!cancelled) setLoading(false); }
    };
    void load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [courseId, revision, refresh]);
  async function act(path: string, body?: unknown) {
    setBusy(true); setError("");
    try { await request(path, post(body)); setRefresh(n => n + 1); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Course pack action failed"); }
    finally { setBusy(false); }
  }
  return <section className="course-packs" aria-label="Course study packs">
    <div className="section-heading"><div><h2>Course study packs</h2><p className="muted">Verified notes, concepts, and flashcards from {sourceIds.length} selected sources.</p></div><button className="button" disabled={busy || !sourceIds.length} onClick={() => void act(`/courses/${courseId}/study-packs`, { source_ids: sourceIds })}><Icon name="book"/>Generate course study pack</button></div>
    {error && <p role="alert">{error}</p>}
    {loading && <p role="status">Loading course study packs…</p>}
    {!loading && !error && !packs.length && <EmptyState title="Bring the whole course into focus">Choose sources above and create one connected study pack. Every section links back to its original evidence.</EmptyState>}
    {packs.map(pack => <details key={pack.id} className="content-card course-pack" open={active.has(pack.status) || pack.status === "stale"}>
      <summary><span>{pack.title}</span><span className={`status ${pack.status}`}>{pack.status.replaceAll("_", " ")}</span></summary>
      {active.has(pack.status) && <><progress aria-label="Course pack progress" max={100} value={pack.progress} /><p>{pack.status} · {pack.progress}%</p><button className="button secondary" disabled={busy} onClick={() => void act(`/courses/${courseId}/study-packs/${pack.id}/cancel`)}>Cancel pack</button></>}
      {["failed", "cancelled"].includes(pack.status) && <button className="button secondary" disabled={busy} onClick={() => void act(`/courses/${courseId}/study-packs/${pack.id}/retry`)}>Retry pack</button>}
      {pack.status === "stale" && <p role="status">Source material changed. Select current sources and generate a new pack.</p>}
      {pack.error && <p role="alert">{pack.error}</p>}
      {pack.status === "completed" && <p>{pack.quiz_id ? `Mixed quiz saved to the quiz library · ${pack.quiz_status ?? "ready"}` : `Mixed quiz · ${pack.quiz_status ?? "pending"}`}
        {pack.quiz_status === "failed" && <button className="text-button" disabled={busy} onClick={() => void act(`/courses/${courseId}/study-packs/${pack.id}/quiz/retry`)}>Retry mixed quiz</button>}</p>}
      {pack.status === "completed" && !pack.quiz_id && !pack.quiz_status && <button className="button secondary" disabled={busy} onClick={() => void act(`/courses/${courseId}/study-packs/${pack.id}/import-quizzes`)}>Import saved quiz items</button>}
      {pack.quiz_id && <Link className="button secondary" to={`/courses/${courseId}/practice#quiz-${pack.quiz_id}`}>Open mixed quiz →</Link>}
      {pack.warnings.map(w => <p className="editing-note" key={w}>{w}</p>)}
      {pack.overview && <p>{pack.overview}</p>}
      {pack.overview_evidence?.map(e => <Link className="text-button" key={e.chunk_id} to={citationHref(courseId, e)}>{citationLabel(e)}</Link>)}
      {pack.sections.map(section => <section key={section.key}>
        <h3>{section.title}</h3>
        {section.status === "unsupported" && <p>Coverage gap: {section.reason}</p>}
        {section.content.items.map((item, index) => item.kind === "flashcard" ? <Flashcard key={`${item.kind}-${index}`} question={item.title} answer={item.text}>
          <div className="pack-evidence">{item.chunk_ids.map(id => { const e = section.evidence.find(e => e.chunk_id === id); return e ? <Link className="text-button" key={id} to={citationHref(courseId, e)}>{citationLabel(e)}</Link> : null; })}</div>
        </Flashcard> : <article className="content-card" key={`${item.kind}-${index}`}>
          <p className="eyebrow">{item.kind}</p><h4>{item.title}</h4>
          {item.kind === "quiz" ? <><ol>{item.options.map((option, i) => <li key={i}>{option}</li>)}</ol><details><summary>Show answer</summary><p>{item.correct_answer != null ? item.options[item.correct_answer] : ""}</p><p>{item.text}</p></details></> : <p>{item.text}</p>}
          <div className="pack-evidence">{item.chunk_ids.map(id => { const e = section.evidence.find(e => e.chunk_id === id); return e ? <Link className="text-button" key={id} to={citationHref(courseId, e)}>{citationLabel(e)}</Link> : null; })}</div>
        </article>)}
      </section>)}
      <section aria-label="Source coverage"><h3>Source coverage</h3>
        <p>{pack.coverage.cited_sources?.length ?? 0} of {pack.source_snapshots.length} selected sources cited.</p>
        <ul>{pack.source_snapshots.map(s => <li key={s.id}>{s.name} · {pack.coverage.cited_sources?.includes(s.id) ? "Cited" : pack.coverage.omitted_sources?.find(o => o.source_id === s.id)?.reason ?? "Pending"}</li>)}</ul>
      </section>
    </details>)}
  </section>;
}
