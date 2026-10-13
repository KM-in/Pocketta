import { useId, useState } from "react";
import type { StudyPack } from "../types";
import { Flashcard } from "./Flashcard";
import { EvidenceLinks } from "./EvidenceLinks";

type Tab = "notes" | "concepts" | "flashcards" | "quiz";

export function StudyPackView({ pack, initialTab = "notes" }: { pack: StudyPack; initialTab?: Tab }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [answers, setAnswers] = useState<Record<number, number>>({});

  const id = useId();
  const tabs: Tab[] = ["notes", "concepts", "flashcards", "quiz"];
  return (
    <section className="study-pack" aria-labelledby="study-pack-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Study pack</p>
          <h2 id="study-pack-heading">{pack.title}</h2>
        </div>
      </div>
      <p className="overview">{pack.overview}</p>
      <div className="tabs" role="tablist" aria-label="Study pack sections">
        {tabs.map((item) => (
          <button
            type="button"
            role="tab"
            id={`${id}-${item}`}
            aria-controls={`${id}-panel`}
            tabIndex={tab === item ? 0 : -1}
            onKeyDown={event => {
              let next = tabs.indexOf(item);
              if (event.key === "ArrowRight") next = (next + 1) % tabs.length;
              else if (event.key === "ArrowLeft") next = (next + tabs.length - 1) % tabs.length;
              else if (event.key === "Home") next = 0;
              else if (event.key === "End") next = tabs.length - 1;
              else return;
              event.preventDefault(); setTab(tabs[next]); document.getElementById(`${id}-${tabs[next]}`)?.focus();
            }}
            aria-selected={tab === item}
            className={tab === item ? "active" : ""}
            onClick={() => setTab(item)}
            key={item}
          >
            {item}
          </button>
        ))}
      </div>

      {tab === "quiz" && <p className="quiz-status" role="status">{Object.keys(answers).length} of {pack.quiz.length} answered · {Object.entries(answers).filter(([index, answer]) => pack.quiz[Number(index)].correct_answer === answer).length} correct. Answers are not saved.</p>}
      <div className="cards" data-section={tab} id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${tab}`} tabIndex={0}>
        {pack[tab].length === 0 && <p className="muted">No {tab} were generated in this pack.</p>}
        {tab === "notes" &&
          pack.notes.map((note) => (
            <article className="content-card" key={`${note.title}-${note.segment_ids[0]}`}>
              <h3>{note.title}</h3>
              <p>{note.body}</p>
              <EvidenceLinks ids={note.segment_ids} />
            </article>
          ))}
        {tab === "concepts" &&
          pack.concepts.map((concept) => (
            <article className="content-card" key={`${concept.name}-${concept.segment_ids[0]}`}>
              <h3>{concept.name}</h3>
              <p>{concept.definition}</p>
              <EvidenceLinks ids={concept.segment_ids} />
            </article>
          ))}
        {tab === "flashcards" &&
          pack.flashcards.map((card, index) => (
            <Flashcard key={`${card.front}-${index}`} question={card.front} answer={card.back} label={`Recall · ${index + 1} of ${pack.flashcards.length}`}>
              <EvidenceLinks ids={card.segment_ids} />
            </Flashcard>
          ))}
        {tab === "quiz" &&
          pack.quiz.map((question, questionIndex) => {
            const selected = answers[questionIndex];
            return (
              <article className="content-card quiz" key={`${question.question}-${questionIndex}`}>
                <h3>{questionIndex + 1}. {question.question}</h3>
                <div className="options">
                  {question.options.map((option, optionIndex) => {
                    const revealed = selected !== undefined;
                    const correct = optionIndex === question.correct_answer;
                    const selectedWrong = selected === optionIndex && !correct;
                    return (
                      <button
                        type="button"
                        aria-pressed={selected === optionIndex}
                        className={`${revealed && correct ? "correct" : ""} ${selectedWrong ? "wrong" : ""}`}
                        onClick={() => setAnswers((current) => ({ ...current, [questionIndex]: optionIndex }))}
                        key={option}
                      >
                        {String.fromCharCode(65 + optionIndex)}. {option}{revealed && correct ? " · Correct answer" : selectedWrong ? " · Your answer — incorrect" : ""}
                      </button>
                    );
                  })}
                </div>
                {selected !== undefined && <div aria-live="polite"><p className="answer-outcome">{selected === question.correct_answer ? "Correct. Well done." : "Not quite. Review the correct answer and evidence."}</p><p className="explanation">{question.explanation}</p></div>}
                <EvidenceLinks ids={question.segment_ids} />
              </article>
            );
          })}
      </div>
    </section>
  );
}
