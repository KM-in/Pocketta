import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Link, Route, Routes, useNavigate, useParams, useLocation } from "react-router-dom";
import { API_BASE, api, request, uploadRequest, type UploadProgress } from "../api/client";
import { LecturePage, ReadinessDetails } from "./LecturePage";
import { CourseTutor } from "./CourseTutor";
import { CitationFocus } from "./CitationFocus";
import { CourseKnowledge } from "./CourseKnowledge";
import { CoursePacks } from "./CoursePacks";
import { QuizWorkspace } from "./QuizWorkspace";
import { Recorder } from "./Recorder";
import { StudyPackView } from "./StudyPackView";
import { EvidenceContext } from "./EvidenceLinks";
import type { HealthResponse, LectureDetail, StudyPack } from "../types";

export interface Course { id: string; title: string; description: string; source_count?: number }
interface Unit { id: string; location: string; text: string; native_text: string; uncertain: boolean; preview_url: string | null }
interface Source { id: string; course_id: string; name: string; type: string; version: number; status: string; progress: number; error: string | null; content_units: Unit[]; study_pack: null | Record<string, unknown>; asset_url: string; knowledge?: { status: string; error: string | null; summaries?: { status: string; count: number; error: string | null }; embeddings?: { status: string; count: number } }; knowledge_status?: string }
const ACTIVE = new Set(["queued", "extracting", "indexing", "generating", "normalizing", "transcribing", "deleting"]);
const stamp = (ms: number) => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;
function locationLabel(location: string) {
  if (location.startsWith("time:")) return stamp(Number(location.split(":")[1].split("-")[0]));
  return location.replace(":", " ");
}
function adaptPack(pack: Record<string, unknown>): StudyPack {
  const result = { ...pack };
  for (const key of ["notes", "concepts", "flashcards", "quiz"]) {
    result[key] = (pack[key] as Array<Record<string, unknown>>).map(item => ({ ...item, segment_ids: item.content_unit_ids }));
  }
  return result as unknown as StudyPack;
}

export default function CourseWorkspace() {
  return <BrowserRouter><Routes><Route path="/" element={<Workspace />} /><Route path="/courses/:courseId" element={<Workspace />} /><Route path="/courses/:courseId/tutor" element={<Workspace />} /><Route path="/courses/:courseId/sources/:sourceId" element={<Workspace />} /><Route path="*" element={<Workspace />} /></Routes></BrowserRouter>;
}

function Workspace() {
  const { courseId, sourceId } = useParams();
  const navigate = useNavigate();
  const tutorPage = useLocation().pathname.endsWith("/tutor");
  const [courses, setCourses] = useState<Course[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const chosenIds = chosen.filter(id => sources.some(s => s.id === id && s.course_id === courseId));
  useEffect(() => { setChosen([]); }, [courseId]);
  const [selected, setSelected] = useState<Source | null>(null);
  const [lecture, setLecture] = useState<LectureDetail | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [transfer, setTransfer] = useState<UploadProgress | null>(null);
  const [setup, setSetup] = useState(false);
  const [form, setForm] = useState<"new" | "edit" | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [revision, setRevision] = useState(0);
  const route = useRef("");
  route.current = `${courseId}/${sourceId}`;
  const course = courses.find(c => c.id === courseId);
  const refresh = () => setRevision(n => n + 1);

  useEffect(() => { setForm(null); setTransfer(null); }, [courseId, sourceId]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setSources([]); setSelected(null); setLecture(null); setError("");
    const load = async () => {
      try {
        const [nextCourses, nextHealth, nextSources] = await Promise.all([
          request<Course[]>("/courses"), api.health(), courseId ? request<Source[]>(`/courses/${courseId}/sources`) : Promise.resolve([]),
        ]);
        const summary = sourceId ? nextSources.find(s => s.id === sourceId) : null;
        const source = summary ? await request<Source>(`/sources/${summary.id}`) : null;
        if (sourceId && !source) throw new Error("Source does not belong to this course or no longer exists");
        const nextLecture = source?.type === "recording" ? await api.get(source.id) : null;
        if (cancelled) return;
        setCourses(nextCourses); setHealth(nextHealth); setSources(nextSources); setSelected(source ?? null); setLecture(nextLecture);
        if (nextSources.some(s => ACTIVE.has(s.status) || ["queued", "indexing"].includes(s.knowledge_status ?? "") || ["queued", "indexing"].includes(s.knowledge?.summaries?.status ?? ""))) timer = setTimeout(() => void load(), 1500);
      } catch (cause) { if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load workspace"); }
    };
    void load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [courseId, sourceId, revision]);

  async function act(fn: () => Promise<unknown>, target?: string) {
    setBusy(true); setError("");
    try { await fn(); if (!target || route.current === target) refresh(); }
    catch (cause) { if (!target || route.current === target) setError(cause instanceof Error ? cause.message : "Action failed"); }
    finally { setBusy(false); }
  }
  async function upload(file?: File) {
    if (!file || !courseId) return;
    const target = route.current;
    await act(async () => {
      const body = new FormData(); body.append("file", file);
      setTransfer({ loaded: 0, total: null, transferred: false });
      let source: Source;
      try {
        source = await uploadRequest<Source>(`/courses/${courseId}/sources`, body, progress => {
          if (route.current === target) setTransfer(progress);
        });
      } finally {
        if (route.current === target) setTransfer(null);
      }
      if (route.current === target) navigate(`/courses/${courseId}/sources/${source.id}`);
    }, target);
  }
  async function uploadFiles(files: FileList) {
    if (files.length === 1) return upload(files[0]);
    if (!courseId || !files.length) return;
    const target = route.current, list = Array.from(files);
    await act(async () => {
      let next = 0;
      const loaded = list.map(() => 0), errors: string[] = [];
      const total = list.reduce((sum, file) => sum + file.size, 0);
      setTransfer({ loaded: 0, total, transferred: false });
      async function worker() {
        while (next < list.length) {
          const index = next++, body = new FormData(); body.append("file", list[index]);
          try {
            await uploadRequest<Source>(`/courses/${courseId}/sources`, body, progress => {
              loaded[index] = Math.min(progress.loaded, list[index].size);
              if (route.current === target) setTransfer({ loaded: loaded.reduce((a, b) => a + b, 0), total, transferred: loaded.reduce((a, b) => a + b, 0) === total });
            });
          } catch { errors.push(list[index].name); }
          if (route.current === target) refresh();
        }
      }
      try { await Promise.all([worker(), worker()]); }
      finally { if (route.current === target) setTransfer(null); }
      if (errors.length) throw new Error(`Some uploads failed: ${errors.join(", ")}. Successful uploads were kept.`);
    }, target);
  }
  async function removeSource() {
    if (!selected || !confirm(`Permanently delete “${selected.name}” and its generated data?`)) return;
    await act(async () => { await request(`/sources/${selected.id}`, { method: "DELETE" }); navigate(`/courses/${courseId}`); });
  }
  async function sourceAction(action: string) {
    if (!selected) return;
    await act(() => request(`/sources/${selected.id}/${action}`, { method: "POST" }));
  }
  const evidence = Object.fromEntries((selected?.content_units ?? []).flatMap(u => {
    const entry = { label: `${selected?.name} · ${locationLabel(u.location)}`, href: `/courses/${courseId}/sources/${selected!.id}?citation=${encodeURIComponent(u.id)}&version=${selected!.version}`, target: u.location.startsWith("time:") ? u.location.split(":").slice(2).join(":") : u.id };
    return [[u.id, entry], ...(u.location.startsWith("time:") ? [[entry.target, entry]] : [])];
  }));

  return <div className="app-shell">
    <aside className="sidebar">
      <Link className="brand" to="/"><div className="brand-mark">P</div><div><strong>PocketTA</strong><span>Course study desk</span></div></Link>
      <button className="button" disabled={busy} onClick={() => { setTitle(""); setDescription(""); setForm("new"); }}>＋ New course</button>
      <nav className="lecture-list" aria-label="Courses"><p className="nav-label">Your courses</p>
        {!courses.length && <p className="empty-list">Create your first course.</p>}
        {courses.map(c => <Link className={`course-link ${c.id === courseId ? "selected" : ""}`} key={c.id} to={`/courses/${c.id}`}><strong>{c.title}</strong><small>{c.source_count ?? 0} sources</small></Link>)}
      </nav>
      <button className="button secondary" onClick={() => setSetup(!setup)}>Engine & storage</button>
      <p className="course-privacy">{health?.components.cerebras ? "Cloud mode: relevant source text and selected page images are sent to the configured cloud provider." : "Local text generation. Document vision requires cloud provider configuration."} Embeddings send source chunks, summaries, and queries to the configured embedding provider when enabled.</p>
    </aside>
    <main className="workspace-main">
      {error && <div role="alert" className="error-banner">{error}<button className="text-button" onClick={refresh}>Retry connection</button></div>}
      {transfer && <section className="processing-card" aria-live="polite" aria-label="Upload transfer">
        <p>{transfer.transferred ? "Upload complete; waiting for server" : transfer.total ? `Uploading · ${Math.floor(transfer.loaded / transfer.total * 100)}%` : "Uploading…"}</p>
        {!transfer.transferred && <progress aria-label="Upload progress" max={transfer.total ?? undefined} value={transfer.total ? transfer.loaded : undefined} />}
      </section>}
      {setup && health && <section className="setup-card"><h2>Engine & storage</h2><ReadinessDetails health={health} /></section>}
      {form && <form className="setup-card course-form" aria-label={form === "new" ? "New course" : "Edit course"} onSubmit={event => {
        event.preventDefault(); void act(async () => {
          const result = await request<Course>(form === "new" ? "/courses" : `/courses/${courseId}`, { method: form === "new" ? "POST" : "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, description }) });
          setForm(null); navigate(`/courses/${result.id}`);
        });
      }}><h2>{form === "new" ? "Create a course" : "Edit course"}</h2>
        <label>Course title<input aria-label="Course title" required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label>
        <label>Description<textarea aria-label="Course description" maxLength={5000} value={description} onChange={e => setDescription(e.target.value)} /></label>
        <div className="header-actions"><button className="button" disabled={busy || !title.trim()}>Save course</button><button className="button secondary" type="button" onClick={() => setForm(null)}>Cancel</button></div>
      </form>}
      {!courseId && <div className="welcome"><p className="eyebrow">Your material. One workspace.</p><h1>Start with a course.</h1><p>Collect lectures, PDFs, and slides. Build study packs and follow every citation back to your source.</p></div>}
      {course && <>
        <header className="lecture-header"><div><Link to={`/courses/${course.id}`} className="eyebrow">Course workspace</Link><h1>{course.title}</h1><p>{course.description}</p></div>
          <div className="header-actions"><Link className="button" to={`/courses/${courseId}/tutor`}>Course tutor</Link><button className="button secondary" disabled={busy} onClick={() => { setTitle(course.title); setDescription(course.description); setForm("edit"); }}>Edit course</button>
            {!sources.length && <button className="button danger" disabled={busy} onClick={() => { if (confirm(`Delete empty course “${course.title}”?`)) void act(async () => { await request(`/courses/${course.id}`, { method: "DELETE" }); navigate("/"); }); }}>Delete course</button>}
          </div>
        </header>
        {tutorPage && <CourseTutor key={`tutor-${courseId}`} courseId={courseId!} />}
        {!selected && !tutorPage && <>
          <CourseKnowledge key={`knowledge-${courseId}`} courseId={courseId!} sourceIds={chosenIds} />
          <CoursePacks key={`packs-${courseId}`} courseId={courseId!} sourceIds={chosenIds} revision={revision} />
          <QuizWorkspace key={`quizzes-${courseId}`} courseId={courseId!} sourceIds={chosenIds} sources={sources.filter(s => s.course_id === courseId).map(s => ({ id: s.id, name: s.name }))} />
          <label className={`drop-zone ${busy ? "disabled" : ""}`} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) void uploadFiles(e.dataTransfer.files); }}>
            <input aria-label="Upload course source" type="file" multiple accept=".pdf,.pptx,.wav,.mp3,.m4a,.mp4,.webm,.ogg" disabled={busy} onChange={e => { if (e.target.files) void uploadFiles(e.target.files); e.target.value = ""; }} />
            <span className="upload-icon">↑</span><strong>Add course material</strong><span>PDF, PPTX, audio or video · up to 200 MB</span>
          </label>
          <div className="welcome-actions"><button className="button" disabled={busy} onClick={() => void act(async () => { const target = route.current; const demo = await api.demo(courseId); if (target === route.current) navigate(`/courses/${courseId}/sources/${demo.id}`); })}>Try demo in this course</button></div>
          <Recorder key={courseId} disabled={busy} onUse={upload} />
          <section className="course-sources" aria-label="Course sources"><h2>Sources</h2>{!sources.length && <p>No material yet. Upload a source or record a lecture.</p>}
            <div className="header-actions"><label><input type="checkbox" aria-label="Select all ready sources" checked={sources.some(s => !ACTIVE.has(s.status)) && sources.filter(s => !ACTIVE.has(s.status)).every(s => chosenIds.includes(s.id))} onChange={e => setChosen(e.target.checked ? sources.filter(s => !ACTIVE.has(s.status)).map(s => s.id) : [])} /> Select all ready sources</label>
            <button className="button secondary" disabled={busy || !chosenIds.length} onClick={() => void act(() => request(`/courses/${courseId}/index`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_ids: chosenIds }) }))}>Rebuild selected indexes</button></div>
            {sources.filter(s => s.course_id === courseId).map(s => <article className="source-card" key={s.id}>
              <label><input type="checkbox" aria-label={`Select ${s.name}`} disabled={ACTIVE.has(s.status)} checked={chosenIds.includes(s.id)} onChange={e => setChosen(ids => e.target.checked ? [...ids, s.id] : ids.filter(id => id !== s.id))} /> Select</label>
              <Link to={`/courses/${courseId}/sources/${s.id}`}><strong>{s.name}</strong><span>{s.type.toUpperCase()}</span></Link><span className={`status ${s.status}`}>{s.status}</span>
              <p>Passages: {s.knowledge?.status ?? s.knowledge_status ?? "not indexed"} · Summaries: {s.knowledge?.summaries?.status ?? "not indexed"} · Embeddings: {s.knowledge?.embeddings?.status ?? "unavailable"}</p>
              {ACTIVE.has(s.status) && <progress value={s.progress} max={100} />}{s.error && <p>{s.error}</p>}
            </article>)}
          </section>
        </>}
        {selected && selected.course_id === courseId && <EvidenceContext.Provider value={evidence}>
          <Link className="text-button" to={`/courses/${courseId}`}>← All sources</Link>
          <CitationFocus key={`citation-${selected.id}`} courseId={courseId!} sourceId={selected.id} assetUrl={selected.asset_url} recording={selected.type === "recording"} />
          {selected.knowledge && <section className="setup-card" aria-label="Source knowledge index">
            <p>Knowledge index: {selected.knowledge.status.replaceAll("_", " ")}</p>
            <p>Summaries: {selected.knowledge.summaries?.status ?? "not indexed"} · {selected.knowledge.summaries?.count ?? 0} summaries. Embeddings: {selected.knowledge.embeddings?.status ?? "unavailable"}</p>
            {selected.knowledge.summaries?.error && <p className="editing-note">{selected.knowledge.summaries.error}</p>}
            {selected.knowledge.error && <p className="editing-note">{selected.knowledge.error}</p>}
            <button className="button secondary" disabled={busy || ACTIVE.has(selected.status) || ["queued", "indexing"].includes(selected.knowledge.status)} onClick={() => void act(() => request(`/courses/${courseId}/sources/${selected.id}/index`, { method: "POST" }))}>Rebuild search index</button>
          </section>}
          {selected.type === "recording" && lecture ? <LecturePage key={lecture.id} lecture={lecture} busy={busy} remove={removeSource} cancel={() => sourceAction("cancel")} generate={() => sourceAction("generate")} update={payload => act(() => api.update(lecture.id, payload))} /> : <DocumentView key={selected.id} source={selected} busy={busy} remove={removeSource} action={sourceAction} />}
          {selected.type === "recording" && selected.status === "failed" && <button className="button" disabled={busy} onClick={() => void sourceAction("retry")}>Retry source</button>}
        </EvidenceContext.Provider>}
      </>}
    </main>
  </div>;
}

function DocumentView({ source, busy, remove, action }: { source: Source; busy: boolean; remove: () => Promise<void>; action: (action: string) => Promise<void> }) {
  const active = ACTIVE.has(source.status);
  return <div className="lecture-page">
    <header className="lecture-header"><div><p className="eyebrow">{source.type.toUpperCase()}</p><h2>{source.name}</h2><span className={`status ${source.status}`}>{source.status}</span></div>
      <div className="header-actions"><a className="button secondary" target="_blank" rel="noreferrer" href={API_BASE + source.asset_url}>Open original</a>
        {!active && source.content_units.length > 0 && <button className="button" disabled={busy} onClick={() => void action("generate")}>{source.study_pack ? "Regenerate study pack" : "Generate study pack"}</button>}
        {!active && ["failed", "cancelled"].includes(source.status) && <button className="button" disabled={busy} onClick={() => void action("retry")}>Retry extraction</button>}
        {active && <button className="button danger" disabled={busy} onClick={() => void action("cancel")}>Cancel processing</button>}
        <button className="button danger" disabled={busy} onClick={() => void remove()}>Delete source</button>
        {source.study_pack && <a className="button secondary" href={`${API_BASE}/sources/${source.id}/export.md`}>Export Markdown</a>}
      </div>
    </header>
    {active && <section className="processing-card" aria-live="polite"><p>{source.status} · {source.progress}%</p><progress value={source.progress} max={100} /></section>}
    {source.error && <div role="alert" className="failure-card">{source.error}</div>}
    {source.content_units.some(u => u.uncertain) && <p className="editing-note">Some pages have uncertain extraction. Inspect the original; uncertain content is excluded from study-pack generation.</p>}
    {source.study_pack && <StudyPackView key={JSON.stringify(source.study_pack)} pack={adaptPack(source.study_pack)} />}
    <section aria-label="Source content"><h2>Source content</h2>{source.content_units.map(u => <article className={`content-card document-unit ${u.uncertain ? "uncertain" : ""}`} id={u.id} tabIndex={-1} key={u.id}>
      <h3>{locationLabel(u.location)} {u.uncertain ? "· Check extraction" : ""}</h3>
      {u.preview_url && <a href={API_BASE + u.preview_url} target="_blank" rel="noreferrer"><img loading="lazy" src={API_BASE + u.preview_url} alt={`Original ${locationLabel(u.location)}`} /></a>}
      <div><p className="extracted-text">{u.text || "No text extracted."}</p>{u.native_text !== u.text && <details><summary>Native text</summary><p className="extracted-text">{u.native_text || "No native text; vision extraction used."}</p></details>}</div>
    </article>)}</section>
  </div>;
}
