import { createContext, useContext } from "react";
import { Link } from "react-router-dom";
export const EvidenceContext = createContext<Record<string, { label: string; target: string; href?: string }>>({});

export function EvidenceLinks({ ids }: { ids: string[] }) {
  const evidence = useContext(EvidenceContext);
  const visit = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "center" });
    window.setTimeout(() => document.getElementById(id)?.focus(), 450);
  };

  return (
    <div className="evidence" aria-label="Source evidence">
      <span>Evidence</span>
      {ids.map((id) => (
        evidence[id]?.href ? <Link key={id} to={evidence[id].href!}>{evidence[id].label}</Link> : <button key={id} type="button" onClick={() => visit(evidence[id]?.target ?? id)}>
          {evidence[id]?.label ?? id}
        </button>
      ))}
    </div>
  );
}
