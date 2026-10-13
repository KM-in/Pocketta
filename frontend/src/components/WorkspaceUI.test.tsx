import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AppShell, CourseDialog } from "./WorkspaceUI";
import { StudyPackView } from "./StudyPackView";
import type { StudyPack } from "../types";

afterEach(() => { cleanup(); localStorage.clear(); delete document.documentElement.dataset.theme; });
const pack: StudyPack = { title: "Scheduling", overview: "Sharing a processor", notes: [], concepts: [], flashcards: [{ front: "What is a quantum?", back: "A fixed slice of processor time.", segment_ids: [] }], quiz: [{ question: "Which policy rotates?", options: ["FIFO", "Round robin"], correct_answer: 1, explanation: "Round robin rotates the queue.", segment_ids: [] }] };
function shell() { render(<MemoryRouter><AppShell courses={[]} ready={false} setup={false} onSetup={vi.fn()} onNew={vi.fn()} privacy="Local storage"><p>Study workspace</p></AppShell></MemoryRouter>); }

describe("Workspace interactions", () => {
  it("persists the selected theme and supports collapsing navigation", () => {
    localStorage.setItem("pocketta-theme", "light"); shell();
    fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("pocketta-theme")).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
  });
  it("opens and closes the mobile navigation dialog", () => {
    shell();
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(screen.getByRole("dialog", { name: "Navigation" })).toHaveAttribute("open");
    fireEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();
  });
  it("focuses the course title when the native dialog opens", () => {
    const { rerender } = render(<CourseDialog open={false} title="Create a course" onClose={vi.fn()}><input aria-label="Title" /></CourseDialog>);
    rerender(<CourseDialog open title="Create a course" onClose={vi.fn()}><input aria-label="Title" /></CourseDialog>);
    expect(screen.getByLabelText("Title")).toHaveFocus();
  });
  it("supports arrow keys in pack tabs and flashcard answer reveal", () => {
    render(<StudyPackView pack={pack} />);
    fireEvent.keyDown(screen.getByRole("tab", { name: "notes" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "concepts" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "concepts" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "flashcards" }));
    const summary = screen.getByText("Reveal answer");
    expect(summary.parentElement).not.toHaveAttribute("open");
    fireEvent.click(summary);
    expect(summary.parentElement).toHaveAttribute("open");
  });
  it("opens practice directly and communicates answer correctness without relying on color", () => {
    render(<StudyPackView pack={pack} initialTab="quiz" />);
    expect(screen.getByRole("tab", { name: "quiz" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("button", { name: "A. FIFO" }));
    expect(screen.getByRole("button", { name: /Your answer — incorrect/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /B. Round robin · Correct answer/ })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1 of 1 answered · 0 correct");
  });
});
