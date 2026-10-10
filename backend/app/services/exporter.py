from __future__ import annotations

from ..models import LectureDetail


def render_markdown(lecture: LectureDetail, model_provider: str = "lm_studio") -> str:
    if not lecture.transcript or not lecture.study_pack:
        raise ValueError("Lecture is not ready for export")
    pack = lecture.study_pack
    uncertain = [
        segment for segment in lecture.transcript.segments if segment.uncertain
    ]
    lines = [
        f"# {_escape_inline(lecture.title)}",
        "",
        "## Recording metadata",
        "",
        f"- **Source file:** {_escape_inline(lecture.original_filename)}",
        f"- **Duration:** {_duration(lecture.transcript.duration_ms)}",
        f"- **Created:** {lecture.created_at.isoformat()}",
        (
            "- **Processing:** Generated with Cerebras cloud processing; recording transcription runs locally."
            if model_provider == "cerebras"
            else "- **Processing:** Generated locally with PocketTA; no cloud AI is required."
        ),
        "",
        "## Summary",
        "",
        pack.overview,
        "",
        "## Uncertainty warnings",
        "",
    ]
    if uncertain:
        lines.append(
            f"{len(uncertain)} transcript segment(s) were marked uncertain and excluded "
            "from evidence for confident study material: "
            + ", ".join(f"[{segment.id}](#{segment.id})" for segment in uncertain)
        )
    else:
        lines.append("No transcript segments were marked uncertain.")
    lines.extend(["", "## Notes", ""])
    for note in pack.notes:
        lines.extend(
            [f"### {note.title}", "", note.body, "", _evidence(note.segment_ids), ""]
        )
    lines.extend(["## Concepts", ""])
    for concept in pack.concepts:
        lines.extend(
            [
                f"### {concept.name}",
                "",
                concept.definition,
                "",
                _evidence(concept.segment_ids),
                "",
            ]
        )
    lines.extend(["## Flashcards", ""])
    for index, card in enumerate(pack.flashcards, start=1):
        lines.extend(
            [
                f"### Card {index}",
                "",
                f"**Front:** {card.front}",
                "",
                f"**Back:** {card.back}",
                "",
                _evidence(card.segment_ids),
                "",
            ]
        )
    lines.extend(["## Quiz", ""])
    for index, question in enumerate(pack.quiz, start=1):
        lines.extend([f"### {index}. {question.question}", ""])
        for option_index, option in enumerate(question.options):
            lines.append(
                f"- {'**' if option_index == question.correct_answer else ''}{option}{'**' if option_index == question.correct_answer else ''}"
            )
        lines.extend(
            [
                "",
                f"**Explanation:** {question.explanation}",
                "",
                _evidence(question.segment_ids),
                "",
            ]
        )
    lines.extend(["## Transcript", ""])
    for segment in lecture.transcript.segments:
        uncertainty = " ⚠️ uncertain" if segment.uncertain else ""
        lines.extend(
            [
                f'<a id="{segment.id}"></a>',
                f"**[{_timestamp(segment.start_ms)}] {segment.id}{uncertainty}**  ",
                segment.text,
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _evidence(segment_ids: list[str]) -> str:
    links = ", ".join(f"[{item}](#{item})" for item in segment_ids)
    return f"**Evidence:** {links}"


def _timestamp(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


def _duration(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _escape_inline(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for character in ("`", "*", "_", "[", "]", "<", ">", "#", "|"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped.replace("\r", " ").replace("\n", " ")
