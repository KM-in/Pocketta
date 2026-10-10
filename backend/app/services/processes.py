from __future__ import annotations

import subprocess
import threading
from pathlib import Path


class ProcessFailed(RuntimeError):
    pass


class ProcessRegistry:
    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()

    def run(
        self,
        lecture_id: str,
        command: list[str],
        cwd: Path | None = None,
        timeout: float | None = None,
    ) -> str:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with self._lock:
            self._processes[lecture_id] = process
        try:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                process.kill()
                process.communicate()
                raise ProcessFailed(
                    "Source conversion timed out; check the file and retry"
                ) from error
        finally:
            with self._lock:
                self._processes.pop(lecture_id, None)
        if process.returncode != 0:
            detail = (stderr or stdout or "unknown process error").strip()[-2000:]
            raise ProcessFailed(detail)
        return stdout

    def terminate(self, lecture_id: str) -> None:
        with self._lock:
            process = self._processes.get(lecture_id)
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
