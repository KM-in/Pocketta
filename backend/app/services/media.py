from __future__ import annotations

import json
import math
from pathlib import Path
import shutil

from ..config import Settings
from .processes import ProcessRegistry


SUPPORTED_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".wav",
    ".webm",
}


class MediaService:
    def __init__(self, settings: Settings, processes: ProcessRegistry):
        self.settings = settings
        self.processes = processes

    def normalize(self, lecture_id: str, source: Path, output: Path) -> int:
        duration_ms = self._probe_duration_ms(lecture_id, source)
        self.processes.run(
            lecture_id,
            [
                self.settings.ffmpeg_path,
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(output),
            ],
        )
        if duration_ms is None:
            duration_ms = self._probe_duration_ms(lecture_id, output)
        if duration_ms is None:
            raise ValueError("FFprobe could not determine the recording duration")
        if duration_ms <= 0:
            raise ValueError("The uploaded recording has no playable duration")
        return duration_ms

    def _probe_duration_ms(self, lecture_id: str, media: Path) -> int | None:
        probe = self.processes.run(
            lecture_id,
            [
                self.settings.ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=duration",
                "-of",
                "json",
                str(media),
            ],
        )
        try:
            payload = json.loads(probe)
        except json.JSONDecodeError as error:
            raise ValueError("FFprobe could not determine the recording duration") from error
        candidates: list[int] = []
        for value in [payload.get("format", {}).get("duration")] + [
            stream.get("duration") for stream in payload.get("streams", [])
        ]:
            duration_ms = _duration_value_ms(value)
            if duration_ms is not None:
                candidates.append(duration_ms)
        return max(candidates) if candidates else None

    def extract_video_frames(
        self, lecture_id: str, media: Path, output_dir: Path, duration_ms: int
    ) -> list[tuple[int, Path]]:
        """Sample up to 20 evenly spaced frames from a video, retaining millisecond offsets."""
        probe = self.processes.run(
            lecture_id,
            [
                self.settings.ffprobe_path,
                "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=index", "-of", "json", str(media),
            ],
        )
        if not json.loads(probe).get("streams"):
            return []
        shutil.rmtree(output_dir, ignore_errors=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        count = min(20, max(1, math.ceil(duration_ms / 60_000)))
        # Leave a full second at the end so low-frame-rate media still has a
        # decodable frame at the final sample position.
        final_offset = max(0, duration_ms - 1000)
        if count == 1:
            offsets = [0]
        else:
            offsets = [round(i * final_offset / (count - 1)) for i in range(count)]
        frames = []
        for offset in offsets:
            output = output_dir / f"frame-{offset:010d}.png"
            self.processes.run(
                lecture_id,
                [
                    self.settings.ffmpeg_path, "-nostdin", "-y",
                    "-ss", f"{offset / 1000:.3f}", "-i", str(media),
                    "-frames:v", "1", "-vf", "scale=1280:-2", str(output),
                ],
                timeout=60,
            )
            if output.is_file() and output.stat().st_size:
                frames.append((offset, output))
        return frames


def _duration_value_ms(value: object) -> int | None:
    if value in (None, "", "N/A"):
        return None
    try:
        seconds = float(str(value))
    except ValueError:
        return None
    if not math.isfinite(seconds):
        return None
    return round(seconds * 1000)
