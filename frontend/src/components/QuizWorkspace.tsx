import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { TutorEvidence } from "./CourseTutor";
import { citationHref, citationLabel } from "./CourseTutor";

interface Question { id: string; kind: "mcq" | "short_answer"; topic: string; prompt: string; options: string[]; chunk_ids: string[]; citations?: TutorEvidence[]; answer?: string; explanation?: string }
interface Attempt { id: string; quiz_id: string; status: string; answers: Record<string, string>; grades: Record<string, { score: number; confidence: number; uncertain: boolean; feedback: string }>; grade_count?: number; question_count?: number; questions: Question[] }
interface Quiz { id: string; title: string; status: string; stale: boolean; pack_id: string | null; instructions: Record<string, unknown>; questions: Question[]; represented_topics: string[]; represented_sources: { id: string; name: string }[]; attempts: { id: string; status: string; created_at: string; score?: number | null }[]; warnings: string[] }
interface Learning { topics: { topic_id: string; title: string; average: number | null; mastered: boolean; weak: boolean; observations: { uncertain: boolean; score: number; response: string; answer: string; explanation: string; feedback: string }[] }[]; known_topics: string[]; syllabus_progress: { has_syllabus: boolean; material_available: number; studied: number; assessed: number; mastered: number; total: number }; syllabus_topics: { id: string; title: string; material_available: boolean; source_ids: string[]; studied_at: string | null }[] }
interface Syllabus { markdown: string; active: boolean; topics: { id: string; title: string; material_available: boolean; source_ids: string[]; evidence: TutorEvidence[]; studied_at: string | null; assessed_at: string | null; mastered_at: string | null }[] }
const post = (body?: unknown) => ({ method: "POST", headers: { "Content-Type": "application/json" }, ...(body ? { body: JSON.stringify(body) } : {}) });
const put = (body: unknown) => ({ method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function QuizWorkspace({ courseId, sourceIds, sources }: { courseId: string; sourceIds: string[]; sources: { id: string; name: string }[] }) {
  const [quizzes, setQuizzes] = useState<Quiz[]>([]); const [learning, setLearning] = useState<Learning | null>(null); const [syllabus, setSyllabus] = useState<Syllabus>({ markdown: "", active: false, topics: [] });
  const [active, setActive] = useState<Attempt | null>(null); const [answers, setAnswers] = useState<Record<string, string>>({}); const [selectedQuiz, setSelectedQuiz] = useState<Quiz | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [count, setCount] = useState(10); const [mcqCount, setMcqCount] = useState(6); const [difficulty, setDifficulty] = useState("adaptive"); const [desired, setDesired] = useState(""); const [excluded, setExcluded] = useState(""); const [instructions, setInstructions] = useState(""); const [syllabusText, setSyllabusText] = useState("");
  async function load() {
    const [q, l, s] = await Promise.all([request<Quiz[]>(`/courses/${courseId}/quizzes`), request<Learning>(`/courses/${courseId}/learning`), request<Syllabus>(`/courses/${courseId}/syllabus`)]);
    setQuizzes(q); setLearning(l); setSyllabus(s); setSyllabusText(s.markdown);
    if (active) { const attempt = await request<Attempt>(`/courses/${courseId}/quiz-attempts/${active.id}`); setActive(attempt); setAnswers(attempt.answers); }
  }
  useEffect(() => { void load().catch(cause => setError(cause instanceof Error ? cause.message : "Could not load quizzes")); }, [courseId]);
  useEffect(() => {
    if (!active || active.status !== "in_progress") return;
    const timer = setTimeout(() => {
      void request(`/courses/${courseId}/quiz-attempts/${active.id}/answers`, put({ answers })).catch(cause => setError(cause instanceof Error ? cause.message : "Could not save quiz answers"));
    }, 350);
    return () => clearTimeout(timer);
  }, [active?.id, active?.status, answers, courseId]);
  async function action(work: () => Promise<void>) { setBusy(true); setError(""); try { await work(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Quiz request failed"); } finally { setBusy(false); } }
  async function generate() {
    if (!sourceIds.length) { setError("Select at least one source first."); return; }
    await action(async () => { const quiz = await request<Quiz>(`/courses/${courseId}/quizzes`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_ids: sourceIds, question_count: count, mcq_count: mcqCount, difficulty, desired_topics: desired.split(",").map(x => x.trim()).filter(Boolean), excluded_topics: excluded.split(",").map(x => x.trim()).filter(Boolean), instructions }) }); setSelectedQuiz(quiz); await load(); });
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
  async function saveSyllabus() { await action(async () => { const result = await request<Syllabus>(`/courses/${courseId}/syllabus`, put({ markdown: syllabusText })); setSyllabus(result); }); }
  async function confirmSyllabus() { await action(async () => { const result = await request<Syllabus>(`/courses/${courseId}/syllabus/confirm`, post({ mappings: syllabus.topics.map(t => ({ topic_id: t.id, source_ids: t.source_ids })) })); setSyllabus(result); await load(); }); }
  async function markStudied(topicId: string, studied: boolean) { await action(async () => { const result = await request<Syllabus>(`/courses/${courseId}/syllabus/topics/${topicId}/studied`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ studied }) }); setSyllabus(result); await load(); }); }
  const inAttempt = Boolean(active && active.status !== "completed");
  return <section className="setup-card" aria-label="Quizzes and learning progress">
    <h2>Quiz library and learning progress</h2>
    <p>Questions combine the selected sources. Answers and explanations appear after grading completes.</p>
    {error && <p role="alert">{error}</p>}
    <details className="content-card"><summary>Generate custom quiz</summary>
      <p>{sourceIds.length} selected sources: {sources.filter(s => sourceIds.includes(s.id)).map(s => s.name).join(", ") || "none"}</p>
      <div className="quiz-options"><label>Questions<input aria-label="Question count" type="number" min={1} max={50} value={count} onChange={e => { const n = Number(e.target.value); setCount(n); if (mcqCount > n) setMcqCount(n); }} /></label><label>Multiple choice<input aria-label="Multiple choice count" type="number" min={0} max={count} value={mcqCount} onChange={e => setMcqCount(Math.max(0, Math.min(count, Number(e.target.value))))} /></label><label>Difficulty<select aria-label="Quiz difficulty" value={difficulty} onChange={e => setDifficulty(e.target.value)}><option value="adaptive">Adaptive</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="challenging">Challenging</option></select></label></div>
      <label>Topics to include (comma separated)<input aria-label="Desired topics" value={desired} onChange={e => setDesired(e.target.value)} /></label><label>Topics to exclude (comma separated)<input aria-label="Excluded topics" value={excluded} onChange={e => setExcluded(e.target.value)} /></label><label>Instructions<textarea aria-label="Quiz instructions" maxLength={3000} value={instructions} onChange={e => setInstructions(e.target.value)} /></label>
      <button className="button" disabled={busy || !sourceIds.length || mcqCount > count} onClick={() => void generate()}>{busy ? "Generating…" : "Generate custom quiz"}</button>
    </details>
    {active && <article className="content-card quiz-attempt"><h3>{selectedQuiz?.title ?? "Quiz"} {active.status === "completed" ? "· Results" : "· In progress"}</h3>
      {active.status === "grading" && <p>Grading saved answers · {active.grade_count ?? 0}/{active.question_count ?? active.questions.length} complete</p>}
      {selectedQuiz?.instructions && <p className="editing-note">Instructions: {String(selectedQuiz.instructions.instructions ?? "Generated for this course")}</p>}
      {active.questions.map((q, index) => { const grade = active.grades?.[q.id]; return <section className="quiz-question" key={q.id}><p className="eyebrow">{index + 1}. {q.topic} · {q.kind === "mcq" ? "Multiple choice" : "Short answer"}</p><h4>{q.prompt}</h4>
        {q.kind === "mcq" ? q.options.map(option => <label className="quiz-option" key={option}><input type="radio" name={q.id} value={option} disabled={!inAttempt || busy} checked={answers[q.id] === option} onChange={() => setAnswers(current => ({ ...current, [q.id]: option }))} />{option}</label>) : <textarea aria-label={`Answer ${index + 1}`} disabled={!inAttempt || busy} value={answers[q.id] ?? ""} onChange={e => setAnswers(current => ({ ...current, [q.id]: e.target.value }))} />}
        {grade && <div role="status"><p>{grade.uncertain ? "Uncertain grade · review the source evidence. " : ""}Score: {Math.round(grade.score * 100)}% · {grade.feedback}</p><p><strong>Answer:</strong> {selectedQuiz?.questions.find(item => item.id === q.id)?.answer}</p><p>{selectedQuiz?.questions.find(item => item.id === q.id)?.explanation}</p></div>}
        <div>{q.citations?.map(c => <Link className="text-button" key={c.chunk_id} to={citationHref(courseId, c)}>{citationLabel(c)}</Link>)}</div>
      </section>; })}
      {inAttempt && <button className="button" disabled={busy} onClick={() => void submit()}>{active.status === "grading" ? "Retry unfinished grading" : "Submit quiz"}</button>}
    </article>}
    <details className="content-card" id="quiz-library" open><summary>Quiz library · {quizzes.length}</summary>
      {quizzes.map(quiz => <article className="quiz-library-item" key={quiz.id}><h3>{quiz.title} {quiz.stale && <span className="status stale">Source changed</span>}</h3><p>{quiz.questions.length} questions · {quiz.attempts?.length ?? 0} attempts {quiz.pack_id ? "· generated with a course pack" : ""}</p><p>Topics: {quiz.represented_topics?.join(", ") || "Unspecified"} · Sources: {quiz.represented_sources?.map(s => s.name).join(", ") || "No source mapping"}</p>{quiz.warnings?.map(w => <p className="editing-note" key={w}>{w}</p>)}
        <button className="button secondary" disabled={busy || quiz.stale} onClick={() => void start(quiz)}>{quiz.attempts?.some(a => a.status === "in_progress" || a.status === "grading") ? "Resume quiz" : "Start / retake"}</button>
        {quiz.attempts?.filter(a => a.status === "completed").map((attempt, i) => <button className="text-button" key={attempt.id} disabled={busy} onClick={() => void review(quiz, attempt.id)}>Review attempt {i + 1}{attempt.score == null ? "" : ` · ${Math.round(attempt.score * 100)}%`}</button>)}
        {quiz.stale && <button className="button secondary" disabled={busy} onClick={() => void action(async () => { await request(`/courses/${courseId}/quizzes/${quiz.id}/retry`, post()); await load(); })}>Regenerate quiz</button>}
      </article>)}
    </details>
    <details className="content-card" open><summary>Learning progress</summary>
      <p>{learning?.syllabus_progress.has_syllabus ? `Syllabus: material ${learning.syllabus_progress.material_available}/${learning.syllabus_progress.total}, studied ${learning.syllabus_progress.studied}/${learning.syllabus_progress.total}, assessed ${learning.syllabus_progress.assessed}/${learning.syllabus_progress.total}, mastered ${learning.syllabus_progress.mastered}/${learning.syllabus_progress.total}.` : "No syllabus set. Progress below covers known course topics without a syllabus completion percentage."}</p>
      {learning?.known_topics.map(title => { const t = learning.topics.find(item => item.title === title); return <p key={title}>{title}: {t?.average == null ? "not confidently assessed" : `${Math.round(t.average * 100)}%`} · {t?.mastered ? "mastered" : t?.weak ? "review recommended" : t ? "in progress" : "not yet assessed"}</p>; })}
      {learning?.topics.filter(t => !learning.known_topics.includes(t.title)).map(t => <p key={t.topic_id}>{t.title}: {t.average == null ? "not confidently assessed" : `${Math.round(t.average * 100)}%`} · {t.mastered ? "mastered" : t.weak ? "review recommended" : "in progress"}</p>)}
      <a className="button secondary" href={`${import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api"}/courses/${courseId}/learning/user_learning.md`}>Download user_learning.md</a>
    </details>
    <details className="content-card"><summary>Syllabus · {syllabus.active ? "active" : "optional"}</summary>
      <label>Syllabus Markdown<textarea aria-label="Syllabus Markdown" rows={8} value={syllabusText} onChange={e => setSyllabusText(e.target.value)} /></label>
      <label>Upload syllabus Markdown<input aria-label="Upload syllabus Markdown" type="file" accept=".md,.markdown,.txt" onChange={e => { const file = e.target.files?.[0]; if (file) void file.text().then(text => setSyllabusText(text)); e.target.value = ""; }} /></label>
      <button className="button secondary" disabled={busy || !syllabusText.trim()} onClick={() => void saveSyllabus()}>Preview topic mapping</button>
      {syllabus.active && <a className="button secondary" href={`${import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api"}/courses/${courseId}/syllabus.md`}>Download syllabus.md</a>}
      {syllabus.topics.map(topic => <article className="syllabus-topic" key={topic.id}><label><input type="checkbox" aria-label={`Mark ${topic.title} studied`} checked={Boolean(topic.studied_at)} disabled={busy || !syllabus.active} onChange={e => void markStudied(topic.id, e.target.checked)} /> Studied</label><strong>{topic.title}</strong><p>{topic.material_available ? "Material available" : "No source material mapped"} · {topic.mastered_at ? "Mastered" : topic.assessed_at ? "Assessed · review if needed" : "Needs assessment"}</p><div>{topic.evidence.map(e => <Link className="text-button" key={e.chunk_id} to={citationHref(courseId, e)}>{citationLabel(e)}</Link>)}</div><div className="source-mapping">{sources.map(source => <label key={source.id}><input type="checkbox" checked={topic.source_ids.includes(source.id)} onChange={e => setSyllabus(current => ({ ...current, topics: current.topics.map(t => t.id === topic.id ? { ...t, source_ids: e.target.checked ? [...t.source_ids, source.id] : t.source_ids.filter(id => id !== source.id) } : t) }))} />{source.name}</label>)}</div></article>)}
      {syllabus.topics.length > 0 && <button className="button" disabled={busy} onClick={() => void confirmSyllabus()}>{syllabus.active ? "Save syllabus mappings" : "Confirm syllabus topics and mappings"}</button>}
    </details>
  </section>;
}
