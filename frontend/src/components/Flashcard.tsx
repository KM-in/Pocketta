import { useState, type ReactNode } from "react";

export function Flashcard({ question, answer, label = "Flashcard", children }: {
  question: string;
  answer: string;
  label?: string;
  children?: ReactNode;
}) {
  const [flipped, setFlipped] = useState(false);

  return (
    <article className="flip-flashcard">
      <button
        type="button"
        className="flashcard-button"
        aria-label={flipped ? `Answer: ${answer} — show question` : `Question: ${question} — show answer`}
        aria-pressed={flipped}
        data-flipped={flipped}
        onClick={() => setFlipped(current => !current)}
      >
        <span className="flashcard-rotor">
          <span className="flashcard-face flashcard-front" aria-hidden={flipped}>
            <span className="flashcard-caption">{label} · Question</span>
            <span className="flashcard-question">{question}</span>
            <span className="flashcard-hint"><span aria-hidden="true">↻</span> Click to reveal answer</span>
          </span>
          <span className="flashcard-face flashcard-back" aria-hidden={!flipped}>
            <span className="flashcard-caption">{label} · Answer</span>
            <span className="flashcard-answer">{answer}</span>
            <span className="flashcard-hint"><span aria-hidden="true">↻</span> Click to see question</span>
          </span>
        </span>
      </button>
      {children && <div className="flashcard-evidence">{children}</div>}
    </article>
  );
}
