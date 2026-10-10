import { createContext, useContext } from "react";
export const EvidenceContext = createContext<Record<string, { label: string; target: string }>>({});

export function EvidenceLinks({ ids }: { ids: string[] }) {
  const evidence = useContext(EvidenceContext);
  const visit = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => document.getElementById(id)?.focus(), 450);
  };

  return (
    <div className="evidence" aria-label="Source evidence">
      <span>Evidence</span>
      {ids.map((id) => (
        <button key={id} type="button" onClick={() => visit(evidence[id]?.target ?? id)}>
          {evidence[id]?.label ?? id}
        </button>
      ))}
    </div>
  );
}
