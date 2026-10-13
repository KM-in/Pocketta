import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Link, Route, Routes, useNavigate, useParams, useLocation } from "react-router-dom";
import { API_BASE, api, request, uploadRequest, type UploadProgress } from "../api/client";
import { LecturePage, ReadinessDetails } from "./LecturePage";
import { CourseTutor } from "./CourseTutor";
import { CitationFocus } from "./CitationFocus";
import { CourseKnowledge } from "./CourseKnowledge";
import { Recorder } from "./Recorder";
import { StudyPackView } from "./StudyPackView";
import { AppShell, CourseDialog, EmptyState, Icon, PageHeader } from "./WorkspaceUI";
import { CoursePacks } from "./CoursePacks";
import { QuizWorkspace } from "./QuizWorkspace";
import { EvidenceContext } from "./EvidenceLinks";
import type { HealthResponse, LectureDetail, StudyPack } from "../types";

export interface Course { id: string; title: string; description: string; source_count?: number }
interface Unit { id: string; location: string; text: string; native_text: string; uncertain: boolean; preview_url: string | null }
interface SourceSummary {
  id: string; course_id: string; name: string; type: string; status: string;
  progress: number; error: string | null; knowledge_status?: string;
  knowledge?: { status: string; error: string | null; summaries?: { status: string; count: number; error: string | null }; embeddings?: { status: string; count: number } };
}
interface Source extends SourceSummary {
  version: number; content_units: Unit[]; study_pack: null | Record<string, unknown>;
  asset_url: string;
}
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
  return <BrowserRouter><Routes><Route path="/" element={<Workspace />} /><Route path="/courses/:courseId" element={<Workspace />} /><Route path="/courses/:courseId/:section" element={<Workspace />} /><Route path="/courses/:courseId/sources/:sourceId" element={<Workspace />} /><Route path="*" element={<Workspace />} /></Routes></BrowserRouter>;
}

function Workspace() {
  const { courseId, sourceId, section } = useParams();
  const navigate = useNavigate();
  const initialTab = useLocation().search.includes("study=quiz") ? "quiz" as const : "notes" as const;
  const tutorPage = section === "tutor";
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [courses, setCourses] = useState<Course[]>([]);
  const [sources, setSources] = useState<SourceSummary[]>([]);
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
    setSources([]); setSelected(null); setLecture(null); setError(""); setLoading(true); setLoadFailed(false);
    const load = async () => {
      try {
        const [nextCourses, nextHealth, nextSources] = await Promise.all([
          request<Course[]>("/courses"), api.health(), courseId ? request<SourceSummary[]>(`/courses/${courseId}/sources`) : Promise.resolve([]),
        ]);
        const summary = sourceId ? nextSources.find(s => s.id === sourceId) : null;
        const source = summary ? await request<Source>(`/sources/${summary.id}`) : null;
        if (sourceId && !source) throw new Error("Source does not belong to this course or no longer exists");
        const nextLecture = source?.type === "recording" ? await api.get(source.id) : null;
        if (cancelled) return;
        setCourses(nextCourses); setHealth(nextHealth); setSources(nextSources); setSelected(source ?? null); setLecture(nextLecture);
        if (nextSources.some(s => ACTIVE.has(s.status) || ["queued", "indexing"].includes(s.knowledge_status ?? "") || ["queued", "indexing"].includes(s.knowledge?.summaries?.status ?? ""))) timer = setTimeout(() => void load(), 1500);
      } catch (cause) { if (!cancelled) { setLoadFailed(true); setError(cause instanceof Error ? cause.message : "Could not load workspace"); } }
      finally { if (!cancelled) setLoading(false); }
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

  const newCourse = () => { setTitle(""); setDescription(""); setForm("new"); };
  return <AppShell courses={courses} courseId={courseId} courseTitle={course?.title} ready={health?.ready} setup={setup} onSetup={() => setSetup(!setup)} onNew={newCourse} privacy={<>{health?.components.cerebras ? "Cloud mode: relevant source text and selected page images are sent to the configured cloud provider." : "Local text generation. Document vision requires cloud provider configuration."} Embeddings send source chunks, summaries, and queries to the configured embedding provider when enabled.</>}>
      {error && !form && <div role="alert" className="error-banner">{error}<button className="text-button" onClick={refresh}>Retry connection</button></div>}
      {transfer && <section className="processing-card" aria-live="polite" aria-label="Upload transfer">
        <p>{transfer.transferred ? "Upload complete; waiting for server" : transfer.total ? `Uploading · ${Math.floor(transfer.loaded / transfer.total * 100)}%` : "Uploading…"}</p>
        {!transfer.transferred && <progress aria-label="Upload progress" max={transfer.total ?? undefined} value={transfer.total ? transfer.loaded : undefined} />}
      </section>}
      {setup && <section className="setup-card runtime-panel"><div className="section-heading"><div><p className="eyebrow">Settings & runtime</p><h2>Engine & storage</h2></div><button className="icon-button" aria-label="Close runtime settings" onClick={() => setSetup(false)}><Icon name="close"/></button></div><p>Originals and study data are stored locally. Provider configuration is managed in the server environment.</p>{health ? <ReadinessDetails health={health} /> : <p role="status">Runtime status unavailable. Check the backend connection.</p>}</section>}
      <CourseDialog open={Boolean(form)} title={form === "new" ? "Create a course" : "Edit course"} onClose={() => setForm(null)}><form className="setup-card course-form" aria-label={form === "new" ? "New course" : "Edit course"} onSubmit={event => {
        event.preventDefault(); void act(async () => {
          const result = await request<Course>(form === "new" ? "/courses" : `/courses/${courseId}`, { method: form === "new" ? "POST" : "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, description }) });
          setForm(null); navigate(`/courses/${result.id}`);
        });
      }}>
        {error && <p role="alert" className="inline-error">{error}</p>}
        <label>Course title<input autoFocus aria-label="Course title" placeholder="e.g. Introduction to biology" required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label>
        <label>Description<textarea aria-label="Course description" maxLength={5000} value={description} onChange={e => setDescription(e.target.value)} /></label>
        <div className="header-actions"><button className="button" disabled={busy || !title.trim()}>Save course</button><button className="button secondary" type="button" onClick={() => setForm(null)}>Cancel</button></div>
      </form></CourseDialog>
      {!courseId && <>
        <PageHeader title="Your courses" description="A little more clarity. A lot more understanding. Pick up where you left off." action={<button className="button" onClick={newCourse}><Icon name="plus"/>New course</button>}/>
        {loading ? <p role="status" className="loading-state">Loading your courses…</p> : loadFailed && !courses.length ? <section className="failure-card"><h2>Your courses couldn’t be loaded</h2><p>We couldn’t retrieve your course list. Check the backend connection and choose “Retry connection” above.</p></section> : courses.length ? <><div className="section-heading"><h2>My courses <span className="count-badge">{courses.length}</span></h2><span className="muted">Your material, organized.</span></div><div className="course-grid">{courses.map((c, index) => <Link className="course-card" key={c.id} to={`/courses/${c.id}`}><div className="course-card-top"><span className="course-symbol"><Icon name="book"/></span><span className="course-number">{String(index + 1).padStart(2, "0")}</span></div><h2>{c.title}</h2><p>{c.description || "Your space for lectures, notes, and better questions."}</p><div className="course-card-footer"><span><Icon name="files"/>{c.source_count ?? 0} sources</span><span className="open-course">Open course <Icon name="arrow"/></span></div></Link>)}</div><div className="study-principle"><Icon name="book"/><div><strong>Learn from the source.</strong><p>Every explanation is a starting point. Follow its evidence back to your own course material.</p></div></div></> : <EmptyState title="Start with your first course" action={<button className="button" onClick={newCourse}>Create Course</button>}>Upload your lecture notes, slides, or recordings and turn them into a study workspace.</EmptyState>}
      </>}
      {courseId && loading && <p className="loading-state" role="status">Loading course material…</p>}
      {courseId && !course && !loading && !error && <EmptyState title="Course not found" action={<Link className="button" to="/">Your courses</Link>}>This course may have been removed. Open another course to continue.</EmptyState>}
      {course && <>
        <header className="lecture-header"><div><p className="eyebrow">{selected ? "Source workspace" : section ? section.replace("packs", "Study packs").replace("progress", "Learning progress") : "Course overview"}</p><h1>{course.title}</h1><p>{course.description}</p></div>
          <div className="header-actions"><Link className="button" to={`/courses/${courseId}/tutor`}>Course tutor</Link><button className="button secondary" disabled={busy} onClick={() => { setTitle(course.title); setDescription(course.description); setForm("edit"); }}>Edit course</button>
            {!sources.length && <button className="button danger" disabled={busy} onClick={() => { if (confirm(`Delete empty course “${course.title}”?`)) void act(async () => { await request(`/courses/${course.id}`, { method: "DELETE" }); navigate("/"); }); }}>Delete course</button>}
          </div>
        </header>
        {tutorPage && <CourseTutor key={`tutor-${courseId}`} courseId={courseId!} />}
        {!selected && !tutorPage && (!section || section === "sources") && <>
          {!section && <><div className="course-stats"><div><span>Course material</span><strong>{sources.length}<small> sources</small></strong></div><div><span>Ready to study</span><strong>{sources.filter(s => ["ready", "completed", "transcribed"].includes(s.status)).length}<small> sources</small></strong></div><div><span>Processing now</span><strong>{sources.filter(s => ACTIVE.has(s.status)).length}<small> sources</small></strong></div></div><div className="quick-actions"><Link to={`/courses/${courseId}/sources`}><Icon name="upload"/><strong>Add sources</strong><span>Bring your course together</span><Icon name="arrow"/></Link><Link to={`/courses/${courseId}/tutor`}><Icon name="spark"/><strong>Ask your tutor</strong><span>Make sense of the difficult parts</span><Icon name="arrow"/></Link><Link to={`/courses/${courseId}/packs`}><Icon name="book"/><strong>Study packs</strong><span>Notes, concepts & flashcards</span><Icon name="arrow"/></Link></div></>}
          <div className="materials-layout"><section className="upload-panel"><div className="section-heading"><div><h2>Add sources</h2><p className="muted">Good learning starts with your material.</p></div></div>
          <label className={`drop-zone ${busy ? "disabled" : ""}`} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) void uploadFiles(e.dataTransfer.files); }}>
            <input aria-label="Upload course source" type="file" multiple accept=".pdf,.ppt,.pptx,.aac,.flac,.wav,.mp3,.m4a,.mp4,.mkv,.mov,.webm,.ogg" disabled={busy} onChange={e => { if (e.target.files) void uploadFiles(e.target.files); e.target.value = ""; }} />
            <span className="upload-icon"><Icon name="upload"/></span><strong>Add course material</strong><span>PDF, PPTX, audio or video · up to 200 MB</span>
          </label>
          <div className="welcome-actions"><button className="button" disabled={busy} onClick={() => void act(async () => { const target = route.current; const demo = await api.demo(courseId); if (target === route.current) navigate(`/courses/${courseId}/sources/${demo.id}`); })}>Try demo in this course</button></div>
          <Recorder key={courseId} disabled={busy} onUse={upload} /></section><CourseKnowledge key={`knowledge-${courseId}`} courseId={courseId!} sourceIds={chosenIds} /></div>
          <section className="course-sources" aria-label="Course sources"><div className="section-heading"><h2>Sources <span className="count-badge">{sources.length}</span></h2><span className="muted">Open a source to study or generate a pack</span></div>{!sources.length && <p>No material yet. Upload a source or record a lecture.</p>}
            <SourceSelection sources={sources} chosen={chosenIds} onChange={setChosen} />
            {chosenIds.length > 0 && <div className="selection-actions" aria-live="polite"><strong>{chosenIds.length} sources selected</strong><Link className="button" to={`/courses/${courseId}/packs`}>Create study pack</Link><Link className="button secondary" to={`/courses/${courseId}/practice`}>Create quiz</Link><button className="button secondary" disabled={busy} onClick={() => void act(() => request(`/courses/${courseId}/index`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_ids: chosenIds }) }))}>Rebuild selected indexes</button></div>}
            {sources.filter(s => s.course_id === courseId).map(s => <article className="source-card" key={s.id}>
              <label className="source-select"><input type="checkbox" aria-label={`Select ${s.name}`} disabled={ACTIVE.has(s.status)} checked={chosenIds.includes(s.id)} onChange={e => setChosen(ids => e.target.checked ? [...ids, s.id] : ids.filter(id => id !== s.id))} /><span className="sr-only">Select source</span></label>
              <span className="source-symbol"><Icon name={s.type === "recording" ? "quiz" : "files"}/></span>
              <Link className="source-details" to={`/courses/${courseId}/sources/${s.id}`}><strong>{s.name}</strong><span>{s.type.toUpperCase()} · Passages: {s.knowledge?.status ?? s.knowledge_status ?? "not indexed"} · Summaries: {s.knowledge?.summaries?.status ?? "not indexed"} · Embeddings: {s.knowledge?.embeddings?.status ?? "unavailable"}</span></Link>
              <span className={`status ${s.status}`}>{s.status}</span>{ACTIVE.has(s.status) && <progress aria-label={`Processing ${s.name}`} value={s.progress} max={100} />}{s.error && <p>{s.error}</p>}
            </article>)}
          </section>
        </>}
        {!selected && ["packs", "practice"].includes(section ?? "") && <details className="source-picker" open={!chosenIds.length}><summary>Choose sources <span className="count-badge">{chosenIds.length} selected</span></summary><p className="muted">Select the material to include. Active processing sources will be available when ready.</p><SourceSelection sources={sources} chosen={chosenIds} onChange={setChosen} showItems /></details>}
        {section === "packs" && <CoursePacks key={`packs-${courseId}`} courseId={courseId!} sourceIds={chosenIds} revision={revision} />}
        {["practice", "progress"].includes(section ?? "") && <QuizWorkspace key={`quizzes-${courseId}`} courseId={courseId!} sourceIds={chosenIds} sources={sources.filter(s => s.course_id === courseId).map(s => ({ id: s.id, name: s.name }))} view={section === "progress" ? "progress" : "practice"} />}
        {selected && selected.course_id === courseId && <EvidenceContext.Provider value={evidence}>
          <Link className="text-button" to={`/courses/${courseId}/sources`}>← All sources</Link>
          <CitationFocus key={`citation-${selected.id}`} courseId={courseId!} sourceId={selected.id} assetUrl={selected.asset_url} recording={selected.type === "recording"} previews={Object.fromEntries(selected.content_units.map(u => [u.id, u.preview_url]))} />
          {selected.knowledge && <section className="setup-card" aria-label="Source knowledge index">
            <p>Knowledge index: {selected.knowledge.status.replaceAll("_", " ")}</p>
            <p>Summaries: {selected.knowledge.summaries?.status ?? "not indexed"} · {selected.knowledge.summaries?.count ?? 0} summaries. Embeddings: {selected.knowledge.embeddings?.status ?? "unavailable"}</p>
            {selected.knowledge.summaries?.error && <p className="editing-note">{selected.knowledge.summaries.error}</p>}
            {selected.knowledge.error && <p className="editing-note">{selected.knowledge.error}</p>}
            <button className="button secondary" disabled={busy || ACTIVE.has(selected.status) || ["queued", "indexing"].includes(selected.knowledge.status)} onClick={() => void act(() => request(`/courses/${courseId}/sources/${selected.id}/index`, { method: "POST" }))}>Rebuild search index</button>
          </section>}
          {selected.type === "recording" && lecture ? <LecturePage initialTab={initialTab} key={`${lecture.id}-${initialTab}`} lecture={lecture} busy={busy} remove={removeSource} cancel={() => sourceAction("cancel")} generate={() => sourceAction("generate")} update={payload => act(() => api.update(lecture.id, payload))} /> : <DocumentView initialTab={initialTab} key={`${selected.id}-${initialTab}`} source={selected} busy={busy} remove={removeSource} action={sourceAction} />}
          {selected.type === "recording" && selected.status === "failed" && <button className="button" disabled={busy} onClick={() => void sourceAction("retry")}>Retry source</button>}
        </EvidenceContext.Provider>}
      </>}
    </AppShell>;
}

function DocumentView({ source, busy, remove, action, initialTab }: { initialTab: "notes" | "quiz"; source: Source; busy: boolean; remove: () => Promise<void>; action: (action: string) => Promise<void> }) {
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
    {source.study_pack && <StudyPackView key={JSON.stringify(source.study_pack)} initialTab={initialTab} pack={adaptPack(source.study_pack)} />}
    <section aria-label="Source content"><h2>Source content</h2>{source.content_units.map(u => <article className={`content-card document-unit ${u.uncertain ? "uncertain" : ""}`} id={u.id} tabIndex={-1} key={u.id}>
      <h3>{locationLabel(u.location)} {u.uncertain ? "· Check extraction" : ""}</h3>
      {u.preview_url && <a href={API_BASE + u.preview_url} target="_blank" rel="noreferrer"><img loading="lazy" src={API_BASE + u.preview_url} alt={`Original ${locationLabel(u.location)}`} /></a>}
      <div><p className="extracted-text">{u.text || "No text extracted."}</p>{u.native_text !== u.text && <details><summary>Native text</summary><p className="extracted-text">{u.native_text || "No native text; vision extraction used."}</p></details>}</div>
    </article>)}</section>
  </div>;
}

function SourceSelection({ sources, chosen, onChange, showItems = false }: { sources: SourceSummary[]; chosen: string[]; onChange: (ids: string[]) => void; showItems?: boolean }) {
  const ready = sources.filter(s => !ACTIVE.has(s.status));
  return <div className="source-selection"><label className="checkbox-label"><input type="checkbox" aria-label="Select all ready sources" checked={ready.length > 0 && ready.every(s => chosen.includes(s.id))} disabled={!ready.length} onChange={event => onChange(event.target.checked ? ready.map(s => s.id) : [])} />Select all ready sources</label>
    {showItems && sources.map(s => <label className="checkbox-label source-choice" key={s.id}><input type="checkbox" aria-label={`Include ${s.name}`} checked={chosen.includes(s.id)} disabled={ACTIVE.has(s.status)} onChange={event => onChange(event.target.checked ? [...chosen, s.id] : chosen.filter(id => id !== s.id))} /><Icon name="files"/><span>{s.name}</span><span className={`status ${s.status}`}>{s.status}</span></label>)}
    {!sources.length && <p className="muted">Add course material in Sources to get started.</p>}
  </div>;
}
