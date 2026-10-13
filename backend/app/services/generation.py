from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, Field, ValidationError

from ..config import Settings
from ..models import (
    Concept,
    Flashcard,
    QuizQuestion,
    StudyPack,
    Transcript,
    TranscriptSegment,
)


class GenerationError(RuntimeError):
    pass


class ChunkPoint(BaseModel):
    point: str = Field(min_length=1)
    segment_ids: list[str] = Field(min_length=1)


class ChunkSummary(BaseModel):
    points: list[ChunkPoint] = Field(min_length=1, max_length=8)


class RichStudyPack(StudyPack):
    concepts: list[Concept] = Field(min_length=3, max_length=10)
    flashcards: list[Flashcard] = Field(min_length=5, max_length=10)
    quiz: list[QuizQuestion] = Field(min_length=5, max_length=8)


ModelT = TypeVar("ModelT", bound=BaseModel)


SYSTEM_PROMPT = (
    "You are PocketTA, a grounded course study assistant. Use only the supplied "
    "source. Never add outside facts. If evidence is missing, omit the item. Return "
    "only valid JSON matching the requested schema. Every factual item must cite one "
    "or more exact supplied evidence IDs in the fields required by the schema."
)


class GenerationService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def text_model(self):
        return self.settings.text_model

    def _validation_outcome(self, outcome):
        pass

    async def generate(self, transcript: Transcript) -> StudyPack:
        if not self.text_model:
            raise GenerationError("Text generation model is not configured")
        reliable_segments = [
            segment for segment in transcript.segments if not segment.uncertain
        ]
        if not reliable_segments:
            raise GenerationError(
                "Transcript saved, but there is not enough reliable speech to build a study pack"
            )

        direct_prompt = _transcript_prompt(transcript, reliable_only=True)
        if len(direct_prompt) > self.settings.generation_chunk_chars:
            summaries: list[ChunkSummary] = []
            for chunk in _chunk_segments(
                reliable_segments,
                max_chars=self.settings.generation_chunk_chars,
                overlap=self.settings.generation_chunk_overlap_segments,
            ):
                valid_ids = {segment.id for segment in chunk}
                try:
                    summary = await self._generate_model(
                        ChunkSummary,
                        _chunk_prompt(chunk),
                        max_tokens=72_000,
                        validator=lambda value, ids=valid_ids: _validate_chunk(
                            value, ids
                        ),
                    )
                except GenerationError:
                    summary = _fallback_chunk_summary(chunk)
                summaries.append(summary)
            prompt = _summary_pack_prompt(summaries)
        else:
            prompt = direct_prompt

        pack_type = (
            RichStudyPack
            if _source_supports_full_pack(reliable_segments)
            else StudyPack
        )
        return await self._generate_model(
            pack_type,
            prompt,
            max_tokens=72_000,
            validator=lambda value: value.validate_evidence(transcript),
        )

    async def _generate_model(
        self,
        model_type: type[ModelT],
        prompt: str,
        *,
        max_tokens: int,
        validator: Callable[[ModelT], ModelT] | None = None,
    ) -> ModelT:
        error_context = ""
        for attempt in range(2):
            payload = {
                "model": self.text_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt + error_context},
                ],
                "temperature": 0.1,
                "max_tokens": max_tokens,
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": f"pocketta_{model_type.__name__.lower()}",
                        "strict": True,
                        "schema": model_type.model_json_schema(),
                    },
                },
            }
            try:
                raw = await self._complete(payload)
                result = model_type.model_validate_json(_extract_json_object(raw))
                result = validator(result) if validator else result
                self._validation_outcome("valid")
                return result
            except (ValidationError, ValueError, json.JSONDecodeError) as error:
                self._validation_outcome("invalid")
                if attempt == 1:
                    raise GenerationError(
                        f"Invalid structured {model_type.__name__}: {error}"
                    ) from error
                error_context = (
                    "\n\nYour previous response failed validation. Repair format and "
                    "citations only; do not add facts. Return the complete corrected JSON. "
                    f"Validation error: {error}"
                )
        raise GenerationError("Structured generation failed")


def _transcript_prompt(transcript: Transcript, *, reliable_only: bool = True) -> str:
    segments = (
        [segment for segment in transcript.segments if not segment.uncertain]
        if reliable_only
        else transcript.segments
    )
    return (
        "Create concise lecture notes and an overview, 3-8 key concepts, 5-10 "
        "flashcards, and 5-8 multiple-choice quiz questions when the supplied source "
        "contains enough material; return fewer rather than inventing content. Each "
        "quiz must have one correct answer. Cite evidence using segment_ids. Segments "
        "marked uncertain were excluded, so do not infer missing content.\n\nSOURCE:\n"
        + "\n".join(_segment_line(segment) for segment in segments)
    )


def _chunk_segments(
    segments: list[TranscriptSegment], *, max_chars: int, overlap: int
) -> list[list[TranscriptSegment]]:
    chunks: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    current_chars = 0
    for segment in segments:
        line_chars = len(_segment_line(segment)) + 1
        if current and current_chars + line_chars > max_chars:
            chunks.append(current)
            current = current[-overlap:] if overlap > 0 else []
            current_chars = sum(len(_segment_line(item)) + 1 for item in current)
        current.append(segment)
        current_chars += line_chars
    if current:
        chunks.append(current)
    return chunks


def _chunk_prompt(chunk: list[TranscriptSegment]) -> str:
    return (
        "Summarize this chronological lecture chunk for later merging. Capture only "
        "its main claims, definitions, steps, examples, and unresolved uncertainty. "
        "Return at most eight concise evidence-linked points.\n\nSOURCE:\n"
        + "\n".join(_segment_line(segment) for segment in chunk)
    )


def _summary_pack_prompt(summaries: list[ChunkSummary]) -> str:
    source = json.dumps(
        [summary.model_dump(mode="json") for summary in summaries], ensure_ascii=False
    )
    return (
        "Build one non-redundant study pack from these chronological chunk summaries. "
        "Use only their claims and exact segment IDs. Preserve meaningful sequence and "
        "omit unsupported items. Create concise notes and an overview, 3-8 concepts, "
        "5-10 flashcards, and 5-8 multiple-choice questions when supported.\n\n"
        f"CHUNK SUMMARIES:\n{source}"
    )


def _validate_chunk(summary: ChunkSummary, valid_ids: set[str]) -> ChunkSummary:
    cited = {segment_id for point in summary.points for segment_id in point.segment_ids}
    invalid = sorted(cited - valid_ids)
    if invalid:
        raise ValueError(f"Unknown transcript segment IDs: {', '.join(invalid)}")
    return summary


def _fallback_chunk_summary(chunk: list[TranscriptSegment]) -> ChunkSummary:
    points = []
    for segment in chunk[:8]:
        text = " ".join(segment.text.split())
        if len(text) > 240:
            text = text[:237].rstrip() + "..."
        points.append({"point": text, "segment_ids": [segment.id]})
    return ChunkSummary(points=points)


def _source_supports_full_pack(segments: list[TranscriptSegment]) -> bool:
    word_count = sum(len(segment.text.split()) for segment in segments)
    return len(segments) >= 20 and word_count >= 250


def _segment_line(segment: TranscriptSegment) -> str:
    return (
        f"{segment.id} [{_timestamp(segment.start_ms)}-{_timestamp(segment.end_ms)}] "
        f"{segment.text}"
    )


def _extract_content(payload: dict) -> str:
    message = payload["choices"][0]["message"]
    content = message.get("content") or message.get("reasoning_content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LM Studio returned no structured response content")
    return content.strip()


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```")
        stripped = stripped.removesuffix("```").strip()
    start = stripped.find("{")
    if start < 0:
        raise ValueError("Response did not contain a JSON object")
    depth = 0
    in_string = False
    escaped = False
    for index, character in enumerate(stripped[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]
    raise ValueError("Response contained incomplete JSON")


def _timestamp(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"
