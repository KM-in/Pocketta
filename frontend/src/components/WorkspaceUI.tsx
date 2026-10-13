import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import type { Course } from "./CourseWorkspace";

export type IconName = "book" | "home" | "files" | "spark" | "quiz" | "chart" | "settings" | "sun" | "moon" | "menu" | "close" | "plus" | "arrow" | "upload";
const paths: Record<IconName, ReactNode> = {
  book: <><path d="M12 5v15M3 4h5a4 4 0 0 1 4 2 4 4 0 0 1 4-2h5v15h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3Z" /></>,
  home: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  files: <><path d="M14 2H6v20h14V8Zm0 0v6h6M9 13h8M9 17h6"/></>,
  spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4"/></>,
  quiz: <><rect x="5" y="4" width="14" height="18" rx="2"/><path d="M9 2h6v4H9Zm0 10 2 2 4-4m-6 8h6"/></>,
  chart: <><path d="M4 3v18h17M8 16v-4m5 4V8m5 8V5"/></>,
  settings: <><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/></>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></>,
  moon: <path d="M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11Z"/>,
  menu: <path d="M4 6h16M4 12h16M4 18h16"/>, close: <path d="m6 6 12 12M6 18 18 6"/>, plus: <path d="M12 5v14M5 12h14"/>, arrow: <path d="M5 12h14m-5-5 5 5-5 5"/>, upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/></>,
};
export function Icon({ name }: { name: IconName }) { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>; }
export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon"><Icon name="book"/></div><h2>{title}</h2><p>{children}</p>{action}</div>;
}
export function PageHeader({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <header className="page-header"><div><p className="eyebrow">Your learning workspace</p><h1>{title}</h1><p>{description}</p></div>{action}</header>;
}
export function CourseDialog({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current; if (open && dialog && !dialog.open) { dialog.showModal(); dialog.querySelector<HTMLInputElement>("input")?.focus(); } if (!open && dialog?.open) dialog.close(); }, [open]);
  return <dialog ref={ref} className="course-dialog" aria-label={title} onCancel={onClose} onClick={event => { if (event.target === event.currentTarget) onClose(); }}><div className="dialog-heading"><h2>{title}</h2><button className="icon-button" aria-label="Close course form" onClick={onClose}><Icon name="close"/></button></div>{children}</dialog>;
}
export function AppShell({ courses, courseId, courseTitle, ready, setup, onSetup, onNew, privacy, children }: { courses: Course[]; courseId?: string; courseTitle?: string; ready: boolean | undefined; setup: boolean; onSetup: () => void; onNew: () => void; privacy: ReactNode; children: ReactNode }) {
  const location = useLocation();
  const [mobile, setMobile] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState(() => { try { const saved = localStorage.getItem("pocketta-theme"); return (saved === "dark" || saved === "light") ? saved : (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); } catch { return "light"; } });
  const mobileDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { document.documentElement.dataset.theme = theme; try { localStorage.setItem("pocketta-theme", theme); } catch { /* Storage may be unavailable in private sessions. */ } }, [theme]);
  useEffect(() => { setMobile(false); }, [location.pathname]);
  useEffect(() => { if (mobile) mobileDialog.current?.showModal(); else mobileDialog.current?.close(); }, [mobile]);
  const sections: [string, string, IconName][] = [["", "Overview", "home"], ["/sources", "Sources", "files"], ["/packs", "Study packs", "book"], ["/tutor", "AI tutor", "spark"], ["/practice", "Practice", "quiz"], ["/progress", "Learning progress", "chart"]];
  const current = courseId ? sections.find(([suffix]) => suffix && location.pathname === `/courses/${courseId}${suffix}`)?.[1] ?? (location.pathname.includes("/sources/") ? "Source viewer" : "Overview") : "My courses";
  function navigation(isMobile = false) { return <>
    <Link className="brand" to="/" onClick={() => setMobile(false)}><div className="brand-mark"><Icon name="book"/></div><div><strong>PocketTA<span className="brand-period">.</span></strong><span>Your study companion</span></div></Link>
    {isMobile && <button className="icon-button drawer-close" aria-label="Close navigation" onClick={() => setMobile(false)}><Icon name="close"/></button>}
    <nav aria-label={isMobile ? "Mobile navigation" : "Main navigation"}>
      <Link className={`nav-item ${!courseId ? "selected" : ""}`} aria-current={!courseId ? "page" : undefined} to="/" title="My courses"><Icon name="home"/><span>My courses</span></Link>
      {courseId && <div className="course-navigation"><p className="nav-label">This course</p>{sections.map(([suffix, label, icon]) => <Link key={label} title={label} className={`nav-item ${current === label ? "selected" : ""}`} aria-current={current === label ? "page" : undefined} to={`/courses/${courseId}${suffix}`}><Icon name={icon}/><span>{label}</span></Link>)}</div>}
    </nav>
    <nav className="course-switcher" aria-label={isMobile ? "Mobile courses" : "Courses"}><p className="nav-label">Your courses <span>{courses.length}</span></p>{courses.map(c => <Link key={c.id} className={`course-link ${c.id === courseId ? "selected" : ""}`} to={`/courses/${c.id}`} title={c.title}><span className="course-initial">{c.title.slice(0, 1)}</span><span className="course-name">{c.title}</span></Link>)}<button className="nav-item new-course-link" onClick={() => { setMobile(false); onNew(); }}><Icon name="plus"/><span>Create course</span></button></nav>
    <div className="sidebar-bottom"><button className={`nav-item ${setup ? "selected" : ""}`} title="Settings & runtime" onClick={() => { setMobile(false); onSetup(); }}><Icon name="settings"/><span>Settings & runtime</span></button><div className="local-note"><span className={`status-dot ${ready ? "is-ready" : ""}`}/><span>{ready === undefined ? "Connecting to backend" : ready ? "Runtime ready" : "Runtime needs attention"}</span></div><div className="course-privacy">{privacy}</div></div>
  </>; }
  return <div className={`app-shell ${collapsed ? "is-collapsed" : ""}`}><a className="skip-link" href="#main-content">Skip to content</a><aside className="sidebar">{navigation()}</aside><dialog className="navigation-drawer" ref={mobileDialog} aria-label="Navigation" onCancel={() => setMobile(false)}>{mobile && navigation(true)}</dialog><div className="app-body"><header className="topbar"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobile(true)}><Icon name="menu"/></button><button className="icon-button desktop-menu" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}><Icon name="menu"/></button><div className="breadcrumbs"><Link to="/">Courses</Link>{courseTitle && <><span>/</span><Link to={`/courses/${courseId}`}>{courseTitle}</Link></>}<span>/</span><strong>{current}</strong></div><div className="topbar-actions"><span className="workspace-label">Personal workspace</span><button className="icon-button" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}><Icon name={theme === "dark" ? "sun" : "moon"}/></button></div></header><main id="main-content" className="workspace-main" tabIndex={-1}>{children}</main></div></div>;
}
