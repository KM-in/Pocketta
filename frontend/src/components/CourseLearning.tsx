import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import { EmptyState } from "./WorkspaceUI";
interface Check { id: string; question: string; check: { question: string } | null; response: string | null; grade: { score: number; confidence: number; uncertain: boolean; feedback: string } | null }
export function CourseLearning({ courseId }: { courseId: string }) {
  const [checks, setChecks] = useState<Check[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { let cancelled = false; void request<Check[]>(`/courses/${courseId}/tutor`).then(turns => { if (!cancelled) setChecks(turns.filter(t => t.check)); }).catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load learning checks"); }).finally(() => { if (!cancelled) setLoading(false); }); return () => { cancelled = true; }; }, [courseId]);
  return <section aria-label="Learning progress"><div className="section-heading"><div><h2>Your understanding checks</h2><p className="muted">Review saved tutor feedback and revisit the ideas that need another look.</p></div></div><p className="editing-note">These are individual checks of your answers, not a prediction of topic mastery. Practice quizzes in source packs are not saved.</p>{loading && <p role="status">Loading saved checks…</p>}{error && <p role="alert">{error}</p>}{!loading && !error && !checks.length && <EmptyState title="Build understanding, one question at a time" action={<Link className="button" to={`/courses/${courseId}/tutor`}>Test my understanding</Link>}>Choose “Test my understanding” in the tutor. Your answers and feedback will appear here.</EmptyState>}{checks.map(check => <article className="content-card learning-check" key={check.id}><span className="status">{check.grade ? check.grade.uncertain ? "Review evidence" : "Assessed" : "Awaiting answer"}</span><h3>{check.check?.question}</h3>{check.grade ? <><p className="check-score">{Math.round(check.grade.score * 100)}% <span>Score · {Math.round(check.grade.confidence * 100)}% confidence</span></p><p>Your answer: {check.response}</p><p>{check.grade.feedback}</p></> : <p>No answer submitted yet.</p>}<Link className="text-button" to={`/courses/${courseId}/tutor`}>Review in tutor →</Link></article>)}</section>;
}
