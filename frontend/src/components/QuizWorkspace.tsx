import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { API_BASE, request } from "../api/client";
import { EmptyState } from "./WorkspaceUI";
import type { TutorEvidence } from "./CourseTutor";
import { citationHref, citationLabel } from "./CourseTutor";

interface Question { id: string; kind: "mcq" | "short_answer" | "numerical"; topic: string; difficulty?: string; prompt: string; options: string[]; chunk_ids: string[]; citations?: TutorEvidence[]; answer?: string; explanation?: string; numeric_answer?: number; tolerance?: number; unit?: string }
interface AssessmentReport { summary: string; weak_topics: string[]; likely_misconceptions: { title: string; explanation: string; question_ids: string[]; confidence: number }[]; next_steps: string[] }
interface Attempt { id: string; quiz_id: string; status: string; answers: Record<string, string>; grades: Record<string, { score: number; confidence: number; uncertain: boolean; feedback: string }>; assessment_report?: AssessmentReport | null; grade_count?: number; question_count?: number; questions: Question[] }
interface Quiz { id: string; title: string; status: string; stale: boolean; pack_id: string | null; instructions: Record<string, unknown>; questions: Question[]; represented_topics: string[]; represented_sources: { id: string; name: string }[]; attempts: { id: string; status: string; created_at: string; score?: number | null }[]; warnings: string[] }
interface Learning { topics: { topic_id: string; title: string; average: number | null; mastery_probability?: number | null; observation_count?: number; recent_mistakes?: number; last_practiced_at?: string | null; mastered: boolean; weak: boolean; observations: { uncertain: boolean; score: number; response: string; answer: string; explanation: string; feedback: string }[] }[]; known_topics: string[]; prerequisites?: Record<string, string[]>; attempts: { quiz_title: string; status: string; score: number | null; created_at: string }[]; syllabus_progress: { has_syllabus: boolean; material_available: number; studied: number; assessed: number; mastered: number; total: number }; syllabus_topics: { id: string; title: string; material_available: boolean; source_ids: string[]; studied_at: string | null }[] }
interface Syllabus { markdown: string; active: boolean; topics: { id: string; title: string; material_available: boolean; source_ids: string[]; evidence: TutorEvidence[]; studied_at: string | null; assessed_at: string | null; mastered_at: string | null }[] }
const post = (body?: unknown) => ({ method: "POST", headers: { "Content-Type": "application/json" }, ...(body ? { body: JSON.stringify(body) } : {}) });
const put = (body: unknown) => ({ method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function QuizWorkspace({ courseId, sourceIds, sources, view = "all" }: { view?: "all" | "practice" | "progress"; courseId: string; sourceIds: string[]; sources: { id: string; name: string }[] }) {
  const hash = useLocation().hash;
  const [loading, setLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [quizzes, setQuizzes] = useState<Quiz[]>([]); const [learning, setLearning] = useState<Learning | null>(null); const [syllabus, setSyllabus] = useState<Syllabus>({ markdown: "", active: false, topics: [] });
  const [active, setActive] = useState<Attempt | null>(null); const [answers, setAnswers] = useState<Record<string, string>>({}); const [selectedQuiz, setSelectedQuiz] = useState<Quiz | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [count, setCount] = useState(10); const [mcqCount, setMcqCount] = useState(6); const [numericalCount, setNumericalCount] = useState(0); const [difficulty, setDifficulty] = useState("adaptive"); const [desired, setDesired] = useState(""); const [excluded, setExcluded] = useState(""); const [instructions, setInstructions] = useState(""); const [syllabusText, setSyllabusText] = useState("");
  async function load(refreshAttempt = true) {
    const [q, l, s] = await Promise.all([request<Quiz[]>(`/courses/${courseId}/quizzes`), request<Learning>(`/courses/${courseId}/learning`), request<Syllabus>(`/courses/${courseId}/syllabus`)]);
    setQuizzes(q); setLearning(l); setSyllabus(s); setSyllabusText(s.markdown);
    if (active && refreshAttempt) { const attempt = await request<Attempt>(`/courses/${courseId}/quiz-attempts/${active.id}`); setActive(attempt); setAnswers(attempt.answers); }
  }
  useEffect(() => {
    let cancelled = false;
    void Promise.all([request<Quiz[]>(`/courses/${courseId}/quizzes`), request<Learning>(`/courses/${courseId}/learning`), request<Syllabus>(`/courses/${courseId}/syllabus`)])
      .then(([q, l, s]) => { if (!cancelled) { setQuizzes(q); setLearning(l); setSyllabus(s); setSyllabusText(s.markdown); } })
      .catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load quizzes"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [courseId]);
  useEffect(() => { if (hash.startsWith("#quiz-")) { const element = document.getElementById(hash.slice(1)); element?.scrollIntoView?.({ block: "center" }); element?.focus({ preventScroll: true }); } }, [hash, quizzes]);
  useEffect(() => {
    if (!active || active.status !== "in_progress" || busy) return;
    let cancelled = false;
    setSaveStatus("saving");
    const timer = setTimeout(() => {
      void request(`/courses/${courseId}/quiz-attempts/${active.id}/answers`, put({ answers }))
        .then(() => { if (!cancelled) setSaveStatus("saved"); })
        .catch(cause => { if (!cancelled) { setSaveStatus("error"); setError(cause instanceof Error ? cause.message : "Could not save quiz answers"); } });
    }, 350);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [active?.id, active?.status, answers, courseId, busy]);
  async function action(work: () => Promise<void>) { setBusy(true); setError(""); try { await work(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Quiz request failed"); } finally { setBusy(false); } }
  async function generate() {
    if (!sourceIds.length) { setError("Select at least one source first."); return; }
    await action(async () => { const quiz = await request<Quiz>(`/courses/${courseId}/quizzes`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_ids: sourceIds, question_count: count, mcq_count: mcqCount, numerical_count: numericalCount, difficulty, desired_topics: desired.split(",").map(x => x.trim()).filter(Boolean), excluded_topics: excluded.split(",").map(x => x.trim()).filter(Boolean), instructions }) }); setSelectedQuiz(quiz); await load(); });
  }
  async function startDiagnostic() {
    if (!sourceIds.length) { setError("Select at least one processed course source to start a diagnostic."); return; }
    await action(async () => {
      const quiz = await request<Quiz>(`/courses/${courseId}/quizzes`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_ids: sourceIds, question_count: 6, mcq_count: 3, numerical_count: 0, difficulty: "adaptive", instructions: "Baseline diagnostic for a new learner. Sample the available course topics evenly and use a mix of recognition and short explanation questions. Do not assume prior knowledge." }),
      });
      const attempt = await request<Attempt>(`/courses/${courseId}/quizzes/${quiz.id}/attempts`, post());
      setSelectedQuiz(quiz); setActive(attempt); setAnswers(attempt.answers ?? {}); await load();
    });
  }
  async function start(quiz: Quiz) {
    await action(async () => { const inProgress = quiz.attempts?.find(a => a.status === "in_progress" || a.status === "grading"); const attempt = inProgress ? await request<Attempt>(`/courses/${courseId}/quiz-attempts/${inProgress.id}`) : await request<Attempt>(`/courses/${courseId}/quizzes/${quiz.id}/attempts`, post()); setSelectedQuiz(quiz); setActive(attempt); setAnswers(attempt.answers ?? {}); });
  }
  async function review(quiz: Quiz, attemptId: string) {
    await action(async () => { const attempt = await request<Attempt>(`/courses/${courseId}/quiz-attempts/${attemptId}`); setActive(attempt); setAnswers(attempt.answers); setSelectedQuiz(await request<Quiz>(`/courses/${courseId}/quizzes/${quiz.id}`)); });
  }
  async function submit() {
    if (!active) return;
    await action(async () => { if (active.status === "in_progress") await request(`/courses/${courseId}/quiz-attempts/${active.id}/answers`, put({ answers })); let result: Attempt; try { result = await request<Attempt>(`/courses/${courseId}/quiz-attempts/${active.id}/submit`, post()); } catch (cause) { setActive(await request<Attempt>(`/courses/${courseId}/quiz-attempts/${active.id}`)); throw cause; } setActive(result); setAnswers(result.answers); setSelectedQuiz(await request<Quiz>(`/courses/${courseId}/quizzes/${result.quiz_id}`)); await load(); });
  }
  async function leaveAttempt() {
    if (!active) return;
    await action(async () => {
      if (active.status === "in_progress") await request(`/courses/${courseId}/quiz-attempts/${active.id}/answers`, put({ answers }));
      await load(false); setActive(null); setSelectedQuiz(null);
    });
  }
  async function saveSyllabus() { await action(async () => { const result = await request<Syllabus>(`/courses/${courseId}/syllabus`, put({ markdown: syllabusText })); setSyllabus(result); }); }
  async function confirmSyllabus() { await action(async () => { const result = await request<Syllabus>(`/courses/${courseId}/syllabus/confirm`, post({ mappings: syllabus.topics.map(t => ({ topic_id: t.id, source_ids: t.source_ids })) })); setSyllabus(result); await load(); }); }
  async function markStudied(topicId: string, studied: boolean) { await action(async () => { const result = await request<Syllabus>(`/courses/${courseId}/syllabus/topics/${topicId}/studied`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ studied }) }); setSyllabus(result); await load(); }); }
  const inAttempt = Boolean(active && active.status !== "completed");
  return <section className={`quiz-workspace ${inAttempt ? "taking-quiz" : ""}`} aria-label="Quizzes and learning progress">
    <div className="section-heading"><div><h2>{view === "progress" ? "Your learning, made visible" : "Practice with purpose"}</h2><p className="muted">{view === "progress" ? "See what you have studied, assessed, and understood — grounded in your actual work." : "Questions from your course material. Saved answers. Feedback you can trace to the source."}</p></div></div>
    {loading && <p role="status">Loading quizzes and learning progress…</p>}
    {error && <p role="alert" className="editing-note">{error}</p>}
    {view !== "progress" && <><details className="content-card quiz-builder" id="quiz-generator"><summary>Generate custom quiz</summary>
      <p>{sourceIds.length} selected sources: {sources.filter(s => sourceIds.includes(s.id)).map(s => s.name).join(", ") || "none"}</p>
      <div className="quiz-options"><label>Questions<input aria-label="Question count" type="number" min={1} max={50} value={count} onChange={e => { const n = Number(e.target.value); setCount(n); if (mcqCount + numericalCount > n) { setMcqCount(Math.min(mcqCount, n)); setNumericalCount(Math.max(0, n - Math.min(mcqCount, n))); } }} /></label><label>Multiple choice<input aria-label="Multiple choice count" type="number" min={0} max={count} value={mcqCount} onChange={e => setMcqCount(Math.max(0, Math.min(count - numericalCount, Number(e.target.value))))} /></label><label>Numerical<input aria-label="Numerical question count" type="number" min={0} max={count - mcqCount} value={numericalCount} onChange={e => setNumericalCount(Math.max(0, Math.min(count - mcqCount, Number(e.target.value))))} /></label><label>Difficulty<select aria-label="Quiz difficulty" value={difficulty} onChange={e => setDifficulty(e.target.value)}><option value="adaptive">Adaptive</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="challenging">Challenging</option></select></label></div>
      <label>Topics to include (comma separated)<input aria-label="Desired topics" value={desired} onChange={e => setDesired(e.target.value)} /></label><label>Topics to exclude (comma separated)<input aria-label="Excluded topics" value={excluded} onChange={e => setExcluded(e.target.value)} /></label><label>Instructions<textarea aria-label="Quiz instructions" maxLength={3000} value={instructions} onChange={e => setInstructions(e.target.value)} /></label>
      <button className="button" disabled={busy || !sourceIds.length || !Number.isInteger(count) || count < 1 || count > 50 || !Number.isInteger(mcqCount) || mcqCount < 0 || mcqCount + numericalCount > count} onClick={() => void generate()}>{busy ? "Generating…" : "Generate custom quiz"}</button>
    </details>
    {active && <article className="content-card quiz-attempt"><div className="section-heading"><div><p className="eyebrow">{active.status === "completed" ? "Your results" : "Focused practice"}</p><h3>{selectedQuiz?.title ?? "Quiz"} {active.status === "completed" ? "· Results" : "· In progress"}</h3></div><div className="header-actions"><span className={`status ${active.status}`}>{active.status.replaceAll("_", " ")}</span><button className="text-button" disabled={busy} onClick={() => void leaveAttempt()}>Back to quiz library</button></div></div>
      {active.status === "in_progress" && <div className="quiz-attempt-progress"><span>{active.questions.filter(q => answers[q.id]?.trim()).length} of {active.questions.length} answered</span><span role="status">{saveStatus === "saved" ? "All answers saved" : saveStatus === "error" ? "Answers not saved — retry before leaving" : "Saving answers…"}</span><progress aria-label="Quiz answers completed" value={active.questions.filter(q => answers[q.id]?.trim()).length} max={Math.max(1, active.questions.length)} /></div>}
      {active.status === "grading" && <p>Grading saved answers · {active.grade_count ?? 0}/{active.question_count ?? active.questions.length} complete</p>}
      {selectedQuiz?.instructions && <p className="editing-note">Instructions: {String(selectedQuiz.instructions.instructions ?? "Generated for this course")}</p>}
      {active.questions.map((q, index) => { const grade = active.grades?.[q.id]; return <section className="quiz-question" key={q.id}><p className="eyebrow">{index + 1}. {q.topic} · {q.kind === "mcq" ? "Multiple choice" : q.kind === "numerical" ? "Numerical" : "Short answer"}{q.difficulty && ` · ${q.difficulty}`}</p><h4>{q.prompt}</h4>
        {q.kind === "mcq" ? q.options.map(option => <label className="quiz-option" key={option}><input type="radio" name={q.id} value={option} disabled={active.status !== "in_progress" || busy} checked={answers[q.id] === option} onChange={() => setAnswers(current => ({ ...current, [q.id]: option }))} />{option}</label>) : q.kind === "numerical" ? <label>Answer {q.unit && `(${q.unit})`}<input aria-label={`Answer ${index + 1}`} type="number" step="any" disabled={active.status !== "in_progress" || busy} value={answers[q.id] ?? ""} onChange={e => setAnswers(current => ({ ...current, [q.id]: e.target.value }))} /></label> : <textarea aria-label={`Answer ${index + 1}`} disabled={active.status !== "in_progress" || busy} value={answers[q.id] ?? ""} onChange={e => setAnswers(current => ({ ...current, [q.id]: e.target.value }))} />}
        {grade && <div role="status"><p>{grade.uncertain ? "Uncertain grade · review the source evidence. " : ""}Score: {Math.round(grade.score * 100)}% · {grade.feedback}</p><p><strong>Answer:</strong> {q.kind === "numerical" ? `${q.numeric_answer}${q.unit ? ` ${q.unit}` : ""} (±${q.tolerance})` : selectedQuiz?.questions.find(item => item.id === q.id)?.answer}</p><p>{selectedQuiz?.questions.find(item => item.id === q.id)?.explanation}</p></div>}
        <div>{q.citations?.map(c => <Link className="text-button" key={c.chunk_id} to={citationHref(courseId, c)}>{citationLabel(c)}</Link>)}</div>
      </section>; })}
      {active.status === "completed" && active.assessment_report && <section className="content-card assessment-report" aria-label="Post-assessment report">
        <p className="eyebrow">Assessment review</p><h4>What to work on next</h4><p>{active.assessment_report.summary}</p>
        {active.assessment_report.weak_topics.length > 0 && <p><strong>Topics to review:</strong> {active.assessment_report.weak_topics.join(", ")}</p>}
        {active.assessment_report.likely_misconceptions.map((item, index) => <article className="learning-observation" key={`${item.title}-${index}`}>
          <strong>{item.title}</strong><p>{item.explanation}</p><p className="muted">Likely pattern · {Math.round(item.confidence * 100)}% confidence</p>
          <div>{item.question_ids.flatMap(id => active.questions.find(question => question.id === id)?.citations ?? []).map((citation, citationIndex) => <Link className="text-button" key={`${citation.chunk_id}-${citationIndex}`} to={citationHref(courseId, citation)}>{citationLabel(citation)}</Link>)}</div>
        </article>)}
        {active.assessment_report.next_steps.length > 0 && <><h5>Suggested next steps</h5><ul>{active.assessment_report.next_steps.map((step, index) => <li key={`${step}-${index}`}>{step}</li>)}</ul></>}
      </section>}
      {inAttempt && <button className="button" disabled={busy} onClick={() => void submit()}>{active.status === "grading" ? "Retry unfinished grading" : "Submit quiz"}</button>}
    </article>}
    <details className="content-card" id="quiz-library" open><summary>Quiz library · {quizzes.length}</summary>
      {!loading && !error && !quizzes.length && <EmptyState title="Make room for a little practice">Choose sources above, then generate a custom quiz or a mixed quiz from a course study pack.</EmptyState>}
      {quizzes.map(quiz => <article className="quiz-library-item" id={`quiz-${quiz.id}`} tabIndex={-1} key={quiz.id}><h3>{quiz.title} {quiz.stale && <span className="status stale">Source changed</span>}</h3><p>{quiz.questions.length} {quiz.questions.length === 1 ? "question" : "questions"} · {quiz.attempts?.length ?? 0} attempts {quiz.pack_id ? "· generated with a course pack" : ""}</p><p>Topics: {quiz.represented_topics?.join(", ") || "Unspecified"} · Sources: {quiz.represented_sources?.map(s => s.name).join(", ") || "No source mapping"}</p>{quiz.warnings?.map(w => <p className="editing-note" key={w}>{w}</p>)}
        <button className="button secondary" disabled={busy || quiz.stale} onClick={() => void start(quiz)}>{quiz.attempts?.some(a => a.status === "in_progress" || a.status === "grading") ? "Resume quiz" : "Start / retake"}</button>
        {quiz.attempts?.filter(a => a.status === "completed").map((attempt, i) => <button className="text-button" key={attempt.id} disabled={busy} onClick={() => void review(quiz, attempt.id)}>Review attempt {i + 1}{attempt.score == null ? "" : ` · ${Math.round(attempt.score * 100)}%`}</button>)}
        {quiz.stale && <button className="button secondary" disabled={busy} onClick={() => void action(async () => { await request(`/courses/${courseId}/quizzes/${quiz.id}/retry`, post()); await load(); })}>Regenerate quiz</button>}
      </article>)}
    </details>
    </>}
    {view !== "practice" && <><details className="content-card learning-panel" open><summary>Learning progress</summary>
      <p>{learning?.syllabus_progress.has_syllabus ? `Syllabus: material ${learning.syllabus_progress.material_available}/${learning.syllabus_progress.total}, studied ${learning.syllabus_progress.studied}/${learning.syllabus_progress.total}, assessed ${learning.syllabus_progress.assessed}/${learning.syllabus_progress.total}, mastered ${learning.syllabus_progress.mastered}/${learning.syllabus_progress.total}.` : "No syllabus set. Progress below covers known course topics without a syllabus completion percentage."}</p>
      {learning?.syllabus_progress.has_syllabus && <div className="learning-metrics">{([ ["Material available", learning.syllabus_progress.material_available], ["Studied", learning.syllabus_progress.studied], ["Assessed", learning.syllabus_progress.assessed], ["Mastered", learning.syllabus_progress.mastered] ] as [string, number][]).map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}<small> / {learning.syllabus_progress.total}</small></strong><progress aria-label={label} value={value} max={Math.max(1, learning.syllabus_progress.total)} /></div>)}</div>}
      {learning && <article className="content-card"><h3>Recommended next step</h3><p>{recommendation(learning)}</p>{recommendationTopic(learning) && <button className="button secondary" onClick={() => { setDesired(recommendationTopic(learning)!); document.getElementById("quiz-generator")?.setAttribute("open", ""); document.getElementById("quiz-generator")?.scrollIntoView({ behavior: "smooth", block: "center" }); }}>Practice this topic</button>}</article>}
      {learning && learning.known_topics.length > 0 && learning.topics.every(topic => !topic.observation_count) && <article className="content-card">
        <h3>Start with a baseline</h3><p>There are no graded topic observations yet. A short source-based diagnostic will sample this course and start your learning history.</p>
        <button className="button secondary" disabled={busy || !sourceIds.length} onClick={() => void startDiagnostic()}>{busy ? "Preparing diagnostic…" : "Take baseline diagnostic"}</button>
        {!sourceIds.length && <p className="muted">Select one or more processed sources in the Sources panel first.</p>}
      </article>}
      <h3>Recent assessment history</h3>{learning?.attempts?.slice(0, 5).map((attempt, index) => <p key={`${attempt.quiz_title}-${attempt.created_at}-${index}`}>{attempt.quiz_title} · {attempt.status}{attempt.score == null ? "" : ` · ${Math.round(attempt.score * 100)}%`} · {new Date(attempt.created_at).toLocaleDateString()}</p>)}{learning?.attempts?.length === 0 && <p>No completed assessment attempts yet.</p>}
      {learning && !learning.known_topics.length && !learning.topics.length && <EmptyState title="Understanding grows with practice">Complete a quiz or a tutor understanding check. Your topic observations will appear here.</EmptyState>}
      <div className="topic-list">{learning && [...new Set([...learning.known_topics, ...learning.topics.map(t => t.title)])].map(title => { const t = learning.topics.find(item => item.title === title); return <article className="topic-row" key={title}><div><strong>{title}</strong><p>{learningLabel(t)}</p></div><span className={`status ${t?.mastered ? "completed" : t?.weak ? "failed" : ""}`}>{t?.mastered ? "Mastered" : t?.weak ? "Review recommended" : t ? "In progress" : "Not yet assessed"}</span>{t?.observations?.length ? <details><summary>Review {t.observations.length} observations</summary>{t.observations.map((observation, index) => <div className="learning-observation" key={index}><p>{observation.uncertain ? "Uncertain grade — review the evidence" : `Score: ${Math.round(observation.score * 100)}%`}</p><p>Your answer: {observation.response}</p><p>{observation.feedback}</p>{observation.answer && <p>Expected answer: {observation.answer}</p>}{observation.explanation && <p>{observation.explanation}</p>}</div>)}</details> : null}</article>; })}</div>
      <a className="button secondary" href={`${API_BASE}/courses/${courseId}/learning/user_learning.md`}>Download user_learning.md</a>
    </details>
    <details className="content-card"><summary>Syllabus · {syllabus.active ? "active" : "optional"}</summary>
      <label>Syllabus Markdown<textarea aria-label="Syllabus Markdown" rows={8} value={syllabusText} onChange={e => setSyllabusText(e.target.value)} /></label>
      <label>Upload syllabus Markdown<input aria-label="Upload syllabus Markdown" type="file" accept=".md,.markdown,.txt" onChange={e => { const file = e.target.files?.[0]; if (file) void file.text().then(text => setSyllabusText(text)); e.target.value = ""; }} /></label>
      <button className="button secondary" disabled={busy || !syllabusText.trim()} onClick={() => void saveSyllabus()}>Preview topic mapping</button>
      {syllabus.active && <a className="button secondary" href={`${API_BASE}/courses/${courseId}/syllabus.md`}>Download syllabus.md</a>}
      {syllabus.topics.map(topic => <article className="syllabus-topic" key={topic.id}><label><input type="checkbox" aria-label={`Mark ${topic.title} studied`} checked={Boolean(topic.studied_at)} disabled={busy || !syllabus.active} onChange={e => void markStudied(topic.id, e.target.checked)} /> Studied</label><strong>{topic.title}</strong><p>{topic.material_available ? "Material available" : "No source material mapped"} · {topic.mastered_at ? "Mastered" : topic.assessed_at ? "Assessed · review if needed" : "Needs assessment"}</p><div>{topic.evidence.map(e => <Link className="text-button" key={e.chunk_id} to={citationHref(courseId, e)}>{citationLabel(e)}</Link>)}</div><div className="source-mapping">{sources.map(source => <label key={source.id}><input type="checkbox" checked={topic.source_ids.includes(source.id)} onChange={e => setSyllabus(current => ({ ...current, topics: current.topics.map(t => t.id === topic.id ? { ...t, source_ids: e.target.checked ? [...t.source_ids, source.id] : t.source_ids.filter(id => id !== source.id) } : t) }))} />{source.name}</label>)}</div></article>)}
      {syllabus.topics.length > 0 && <button className="button" disabled={busy} onClick={() => void confirmSyllabus()}>{syllabus.active ? "Save syllabus mappings" : "Confirm syllabus topics and mappings"}</button>}
    </details></>}
  </section>;
}

function recommendationTopic(learning: Learning) {
  const target = learning.topics.find(topic => topic.weak)?.title
    ?? learning.known_topics.find(title => (learning.topics.find(topic => topic.title === title)?.observation_count ?? 0) < 3)
    ?? learning.syllabus_topics.find(topic => topic.material_available && !topic.studied_at)?.title
    ?? null;
  if (!target) return null;
  const unmet = learning.prerequisites?.[target]?.find(name => !learning.topics.find(topic => topic.title === name)?.mastered);
  return unmet ?? target;
}

function recommendation(learning: Learning) {
  const target = learning.topics.find(topic => topic.weak)?.title
    ?? learning.known_topics.find(title => (learning.topics.find(topic => topic.title === title)?.observation_count ?? 0) < 3)
    ?? learning.syllabus_topics.find(topic => topic.material_available && !topic.studied_at)?.title
    ?? null;
  const next = recommendationTopic(learning);
  if (!next) return "Your known topics have recent reliable evidence. Continue with a mixed review quiz.";
  if (target && target !== next) return `Review prerequisite ${next} before returning to ${target}; the course knowledge graph lists it as a dependency.`;
  const topic = learning.topics.find(item => item.title === next);
  if (topic?.weak) return `Review ${next}; recent graded answers show mistakes on this topic.`;
  if ((topic?.observation_count ?? 0) < 3) return `Take a short diagnostic on ${next}; there is not enough reliable evidence to estimate mastery yet.`;
  return `Study ${next}, then take a short check to update your learning history.`;
}

function learningLabel(topic: Learning["topics"][number] | undefined) {
  if (!topic || (topic.observation_count ?? 0) < 3) {
    const observed = topic?.average == null ? "" : ` · ${Math.round(topic.average * 100)}% average across recorded observations`;
    return `insufficient evidence · ${topic?.observation_count ?? 0} reliable observations${observed}`;
  }
  const estimate = topic.mastery_probability == null ? "insufficient evidence" : `estimated mastery ${Math.round(topic.mastery_probability * 100)}%`;
  const mistakes = topic.recent_mistakes ? ` · ${topic.recent_mistakes} recent mistake${topic.recent_mistakes === 1 ? "" : "s"}` : "";
  const observed = topic.average == null ? "" : ` · ${Math.round(topic.average * 100)}% average across recorded observations`;
  return `${estimate} · ${topic.observation_count} reliable observations${mistakes}${observed}`;
}
