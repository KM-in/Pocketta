import { useEffect, useState } from "react";
import { API_BASE } from "../api/client";
import { StudyPackView } from "./StudyPackView";
import { TranscriptView } from "./TranscriptView";
import type { HealthResponse, LectureDetail, LectureStatus, SegmentCorrection } from "../types";
const ACTIVE = new Set<LectureStatus>(["queued", "normalizing", "transcribing", "generating", "deleting"]);

export function ReadinessDetails({ health, onlyFailures = false }: { health: HealthResponse; onlyFailures?: boolean }) {
  const components = Object.entries(health.components).filter(([, value]) => !onlyFailures || !value.ready);
  return <ul className="readiness-details">{components.map(([name, value]) => <li key={name}><strong>{name.replaceAll("_", " ")}</strong><span className={value.ready ? "component-ready" : "component-missing"}>{value.ready ? "Ready" : "Needs attention"}</span><code>{value.detail}</code>{!value.ready && value.remediation && <code className="remediation">{value.remediation}</code>}</li>)}</ul>;
}

export function LecturePage({ lecture, busy, remove, cancel, generate, update }: { lecture: LectureDetail; busy: boolean; remove: () => Promise<void>; cancel: () => Promise<void>; generate: () => Promise<void>; update: (payload: { title?: string; corrections?: SegmentCorrection[] }) => Promise<void> }) {
  const active = ACTIVE.has(lecture.status);
  const [title, setTitle] = useState(lecture.title);
  const [editingTitle, setEditingTitle] = useState(false);
  useEffect(() => setTitle(lecture.title), [lecture.title]);
  const saveTitle = async () => {
    if (!title.trim() || title.trim() === lecture.title) { setEditingTitle(false); return; }
    await update({ title: title.trim() });
    setEditingTitle(false);
  };
  const canGenerate = Boolean(lecture.transcript) && !active && ["failed", "cancelled", "transcribed", "completed"].includes(lecture.status);
  return (
    <div className="lecture-page">
      <header className="lecture-header">
        <div><p className="eyebrow">{active ? "Processing source" : "Lecture"}</p>{editingTitle ? <div className="title-editor"><input value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} aria-label="Lecture title" /><button className="button" type="button" onClick={() => void saveTitle()}>Save</button><button className="button secondary" type="button" onClick={() => { setTitle(lecture.title); setEditingTitle(false); }}>Cancel</button></div> : <div className="editable-title"><h1>{lecture.title}</h1>{!active && <button type="button" className="text-button" onClick={() => setEditingTitle(true)}>Edit title</button>}</div>}<span className={`status ${lecture.status}`}>{lecture.status}</span></div>
        <div className="header-actions">
          {lecture.status === "completed" && <a className="button secondary" href={`${API_BASE}/sources/${lecture.id}/export.md`}>Export Markdown</a>}
          {lecture.status === "completed" && <button className="button secondary" type="button" onClick={() => window.print()}>Print / Save as PDF</button>}
          {canGenerate && <button className="button" type="button" disabled={busy} onClick={() => void generate()}>{lecture.status === "completed" ? "Regenerate" : "Generate study pack"}</button>}
          <button className="button danger" type="button" disabled={busy} onClick={() => void remove()}>Delete permanently</button>
        </div>
      </header>
      {active && lecture.status !== "deleting" && <JobProgress lecture={lecture} disabled={busy} onCancel={cancel} />}
      {lecture.status === "failed" && <div className="failure-card"><p className="eyebrow">Processing stopped</p><h2>We couldn’t finish this lecture.</h2><p>{lecture.error}</p>{lecture.transcript && <p>Your transcript is safe. Retry generation without transcribing again.</p>}</div>}
      {lecture.status === "cancelled" && <div className="failure-card cancelled-card"><p className="eyebrow">Cancelled</p><h2>Processing stopped.</h2><p>Any completed transcript remains available below.</p></div>}
      {lecture.metrics.total_seconds > 0 && <Metrics metrics={lecture.metrics} />}
      {lecture.study_pack && <StudyPackView pack={lecture.study_pack} />}
      {lecture.transcript && <TranscriptView transcript={lecture.transcript} editable={!active} hasStudyPack={Boolean(lecture.study_pack)} onSave={(corrections) => update({ corrections })} />}
    </div>
  );
}

function JobProgress({ lecture, disabled, onCancel }: { lecture: LectureDetail; disabled: boolean; onCancel: () => Promise<void> }) {
  const stages: Array<[LectureStatus, string]> = [["normalizing", "Preparing"], ["transcribing", "Transcribing"], ["generating", "Creating practice"]];
  const order = stages.findIndex(([status]) => status === lecture.status);
  return <section className="processing-card" aria-live="polite"><div className="progress-copy"><p className="eyebrow">{lecture.progress}% complete</p><h2>{lecture.message || statusMessage(lecture.status)}</h2><progress max="100" value={lecture.progress}>{lecture.progress}%</progress><ol className="stage-list">{stages.map(([status, label], index) => <li className={index < order ? "done" : index === order ? "current" : ""} key={status}><span>{index < order ? "✓" : index + 1}</span>{label}</li>)}</ol><p>You can leave this page. Progress is saved in your course.</p></div><button type="button" className="button danger" disabled={disabled} onClick={() => void onCancel()}>Cancel processing</button></section>;
}

function Metrics({ metrics }: { metrics: LectureDetail["metrics"] }) {
  return <section className="metrics" aria-label="Processing metrics"><div><strong>{metrics.total_seconds.toFixed(1)}s</strong><span>Total observed time</span></div>{Object.entries(metrics.stage_seconds).map(([stage, seconds]) => <div key={stage}><strong>{seconds.toFixed(1)}s</strong><span>{stage}</span></div>)}<div><strong>{Math.round(metrics.peak_system_memory_mb)} MB</strong><span>Peak observed system memory</span></div></section>;
}

function statusMessage(status: LectureStatus) {
  return ({ queued: "Waiting for the local worker…", normalizing: "Preparing the recording…", transcribing: "Transcribing recording…", generating: "Building your study pack…", deleting: "Deleting local data…", transcribed: "Transcript ready", cancelled: "Cancelled", completed: "Complete", failed: "Failed" })[status];
}
