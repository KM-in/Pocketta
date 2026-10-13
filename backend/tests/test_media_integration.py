import shutil
import struct
import subprocess

import pytest

from backend.app.config import Settings
from backend.app.services.media import MediaService
from backend.app.services.processes import ProcessRegistry


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg and FFprobe are required for this integration test",
)
def test_video_frame_sampling_keeps_low_fps_end_frame(tmp_path):
    source = tmp_path / "low-fps.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x90:r=1",
            "-t",
            "65",
            "-an",
            "-c:v",
            "mpeg4",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    service = MediaService(
        Settings(
            _env_file=None,
            pocketta_data_dir=tmp_path,
            ffmpeg_path=shutil.which("ffmpeg"),
            ffprobe_path=shutil.which("ffprobe"),
        ),
        ProcessRegistry(),
    )

    frames = service.extract_video_frames(
        "low-fps", source, tmp_path / "frames", duration_ms=65_000
    )

    assert [offset for offset, _ in frames] == [0, 64_000]
    assert all(path.is_file() and path.stat().st_size for _, path in frames)
    assert [struct.unpack(">II", path.read_bytes()[16:24]) for _, path in frames] == [
        (1280, 720),
        (1280, 720),
    ]
