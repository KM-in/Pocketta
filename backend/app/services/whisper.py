from __future__ import annotations

import gc
import json
import math
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Literal

from ..config import Settings
from ..models import Transcript, TranscriptSegment
from .processes import ProcessRegistry

BackendName = Literal["whisper_cpp", "faster_whisper"]
_cuda_dll_handles: list[Any] = []
_cuda_runtime_lock = threading.Lock()
_cuda_runtime_ready = False


class WhisperCppService:
    def __init__(self, settings: Settings, processes: ProcessRegistry):
        self.settings = settings
        self.processes = processes

    def transcribe(self, lecture_id: str, audio: Path, duration_ms: int) -> Transcript:
        output_prefix = audio.parent / "whisper"
        command = [
            str(self.settings.whisper_cli_path),
            "-m",
            str(self.settings.whisper_model_path),
            "-f",
            str(audio),
            "-l",
            "en",
            "-ojf",
            "-of",
            str(output_prefix),
            "-np",
        ]
        if not self.settings.whisper_use_gpu:
            command.append("-ng")
        self.processes.run(lecture_id, command)
        output_path = output_prefix.with_suffix(".json")
        if not output_path.is_file():
            raise RuntimeError("whisper.cpp completed without producing JSON output")
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("Could not read whisper.cpp JSON output") from error
        return transcript_from_whisper(
            payload, duration_ms, self.settings.uncertain_confidence_threshold
        )


class FasterWhisperService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._pipeline: Any | None = None
        # BatchedInferencePipeline has mutable timestamp state. Also avoid loading
        # multiple models into the same GPU when lecture workers run concurrently.
        self._lock = threading.Lock()

    def transcribe(self, lecture_id: str, audio: Path, duration_ms: int) -> Transcript:
        del lecture_id
        with self._lock:
            return self._transcribe(audio, duration_ms)

    def _transcribe(self, audio: Path, duration_ms: int) -> Transcript:
        pipeline = None
        try:
            pipeline = self._load_pipeline()
            options = {}
            if self.settings.faster_whisper_vad_filter:
                options["batch_size"] = self.settings.faster_whisper_batch_size
            segments, _info = pipeline.transcribe(
                str(audio),
                beam_size=self.settings.faster_whisper_beam_size,
                language="en",
                vad_filter=self.settings.faster_whisper_vad_filter,
                **options,
            )
            return transcript_from_faster_whisper(
                list(segments),
                duration_ms,
                self.settings.uncertain_confidence_threshold,
            )
        finally:
            self._pipeline = None
            del pipeline
            _release_accelerator_memory()

    def _load_pipeline(self) -> Any:
        if self._pipeline is None:
            try:
                from faster_whisper import BatchedInferencePipeline, WhisperModel
            except ImportError as error:
                raise RuntimeError(
                    "Faster Whisper is not installed. Run: python -m pip install -r backend/requirements-faster-whisper.txt"
                ) from error
            model_ref = str(_faster_whisper_model_directory(self.settings))
            _prepare_windows_cuda_runtime()
            model = WhisperModel(
                model_ref,
                device="cuda",
                compute_type=self.settings.faster_whisper_compute_type,
                local_files_only=True,
            )
            # Batched inference requires VAD or explicit clips for audio >=30s.
            # Standard inference supports arbitrary lengths with VAD disabled.
            self._pipeline = (
                BatchedInferencePipeline(model=model)
                if self.settings.faster_whisper_vad_filter
                else model
            )
        return self._pipeline


class TranscriptionService:
    def __init__(self, settings: Settings, processes: ProcessRegistry):
        self.settings = settings
        self.whisper_cpp = WhisperCppService(settings, processes)
        self.faster_whisper = FasterWhisperService(settings)

    def selected_backend(self) -> BackendName:
        configured = self.settings.transcription_backend
        if configured == "whisper_cpp":
            return "whisper_cpp"
        if configured == "faster_whisper":
            return "faster_whisper"
        faster_status = faster_whisper_readiness(self.settings)
        return "faster_whisper" if faster_status.ready else "whisper_cpp"

    def transcribe(self, lecture_id: str, audio: Path, duration_ms: int) -> Transcript:
        backend = self.selected_backend()
        if backend == "faster_whisper":
            return self.faster_whisper.transcribe(lecture_id, audio, duration_ms)
        return self.whisper_cpp.transcribe(lecture_id, audio, duration_ms)


class Readiness:
    def __init__(self, ready: bool, detail: str):
        self.ready = ready
        self.detail = detail


def whisper_cpp_readiness(settings: Settings) -> Readiness:
    missing: list[str] = []
    if not settings.executable_available(settings.whisper_cli_path):
        missing.append(
            f"whisper.cpp CLI missing at {settings.whisper_cli_path}. Build whisper.cpp, or set WHISPER_CLI_PATH in .env."
        )
    if not settings.whisper_model_path.is_file():
        missing.append(
            f"Whisper model missing at {settings.whisper_model_path}. Place ggml-base.en.bin there, or set WHISPER_MODEL_PATH in .env."
        )
    if missing:
        return Readiness(False, " ".join(missing))
    return Readiness(
        True, f"using {settings.whisper_cli_path} with {settings.whisper_model_path}"
    )


def faster_whisper_readiness(settings: Settings) -> Readiness:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return Readiness(
            False,
            "Faster Whisper package missing. Run: python -m pip install -r backend/requirements-faster-whisper.txt",
        )

    try:
        import ctranslate2
    except ImportError:
        return Readiness(
            False,
            "CTranslate2 package missing. Run: python -m pip install -r backend/requirements-faster-whisper.txt",
        )

    try:
        from importlib.metadata import version

        if int(version("av").split(".")[0]) >= 19:
            return Readiness(
                False,
                "PyAV 19 is incompatible with the supported Faster Whisper decoder. "
                "Reinstall backend/requirements-faster-whisper.txt (requires av<19).",
            )
        _prepare_windows_cuda_runtime()
    except (ImportError, OSError, RuntimeError) as error:
        return Readiness(False, str(error))

    cuda_count = getattr(ctranslate2, "get_cuda_device_count", None)
    if callable(cuda_count):
        try:
            if int(cuda_count()) < 1:
                return Readiness(
                    False,
                    "No CUDA device detected. Install NVIDIA drivers/CUDA runtime, or use TRANSCRIPTION_BACKEND=whisper_cpp.",
                )
        except (RuntimeError, OSError, ValueError) as error:
            return Readiness(
                False,
                f"CUDA readiness check failed: {error}. Install NVIDIA CUDA cuBLAS/cuDNN runtime libraries.",
            )

    try:
        model_path = _faster_whisper_model_directory(settings)
    except (OSError, ValueError, ImportError) as error:
        return Readiness(
            False,
            f"Faster Whisper model is not prepared locally: {error}. "
            "Set FASTER_WHISPER_MODEL_PATH, or run while online: "
            "python -m backend.app.tools.prepare_faster_whisper",
        )
    return Readiness(True, f"using local model at {model_path}")


def transcript_from_faster_whisper(
    raw_segments: list[Any], duration_ms: int, threshold: float
) -> Transcript:
    segments: list[TranscriptSegment] = []
    for raw in raw_segments:
        text = str(getattr(raw, "text", "")).strip()
        if not text:
            continue
        confidence = _faster_whisper_confidence(raw)
        start_ms = max(0, round(float(getattr(raw, "start", 0.0)) * 1000))
        end_ms = max(start_ms, round(float(getattr(raw, "end", 0.0)) * 1000))
        # Whisper can place its final timestamp beyond the actual recording.
        start_ms = min(start_ms, duration_ms)
        end_ms = min(end_ms, duration_ms)
        segments.append(
            TranscriptSegment(
                id=f"seg-{len(segments) + 1:04d}",
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
                confidence=round(confidence, 4),
                uncertain=confidence < threshold,
            )
        )
    if not segments:
        raise ValueError("Faster Whisper returned no transcript segments")
    return Transcript(language="en", duration_ms=duration_ms, segments=segments)


def transcript_from_whisper(
    payload: dict, duration_ms: int, threshold: float
) -> Transcript:
    raw_segments = payload.get("transcription") or payload.get("segments") or []
    segments: list[TranscriptSegment] = []
    for index, raw in enumerate(raw_segments, start=1):
        offsets = raw.get("offsets", {})
        start_ms = _offset_ms(offsets.get("from", raw.get("start", 0)))
        end_ms = _offset_ms(offsets.get("to", raw.get("end", start_ms)))
        probabilities = [
            float(token["p"])
            for token in raw.get("tokens", [])
            if isinstance(token, dict)
            and isinstance(token.get("p"), (int, float))
            and not str(token.get("text", "")).startswith("[")
        ]
        confidence = sum(probabilities) / len(probabilities) if probabilities else 0.5
        confidence = max(0.0, min(1.0, confidence))
        text = str(raw.get("text", "")).strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                id=f"seg-{len(segments) + 1:04d}",
                start_ms=start_ms,
                end_ms=max(start_ms, end_ms),
                text=text,
                confidence=round(confidence, 4),
                uncertain=confidence < threshold,
            )
        )
    if not segments:
        raise ValueError("whisper.cpp returned no transcript segments")
    return Transcript(language="en", duration_ms=duration_ms, segments=segments)


def _offset_ms(value: object) -> int:
    if isinstance(value, float):
        return max(0, round(value * 1000))
    if isinstance(value, int):
        return max(0, value)
    try:
        return max(0, int(float(str(value))))
    except ValueError:
        return 0


def _faster_whisper_confidence(segment: Any) -> float:
    words = getattr(segment, "words", None) or []
    probabilities = [
        float(word.probability)
        for word in words
        if isinstance(getattr(word, "probability", None), (int, float))
    ]
    if probabilities:
        confidence = sum(probabilities) / len(probabilities)
    else:
        avg_logprob = getattr(segment, "avg_logprob", None)
        if isinstance(avg_logprob, (int, float)):
            confidence = math.exp(float(avg_logprob))
        else:
            confidence = 0.5
    return max(0.0, min(1.0, confidence))


def _faster_whisper_model_directory(settings: Settings) -> Path:
    if settings.faster_whisper_model_path:
        model_path = settings.faster_whisper_model_path
    else:
        from faster_whisper.utils import download_model

        # Use Faster Whisper's own alias mapping (not guessed HF repository names).
        model_path = Path(
            download_model(settings.faster_whisper_model_name, local_files_only=True)
        )
    required = ("config.json", "model.bin", "tokenizer.json")
    missing = [name for name in required if not (model_path / name).is_file()]
    if missing:
        raise ValueError(f"{model_path} is missing {', '.join(missing)}")
    return model_path


def _prepare_windows_cuda_runtime() -> None:
    """Keep wheel DLL directories registered for delayed CTranslate2 loads."""
    if sys.platform != "win32":
        return
    global _cuda_runtime_ready
    with _cuda_runtime_lock:
        if _cuda_runtime_ready:
            return
        import ctypes
        from importlib.util import find_spec

        spec = find_spec("nvidia")
        if spec and spec.submodule_search_locations:
            for root in spec.submodule_search_locations:
                for package in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
                    directory = Path(root) / package / "bin"
                    if directory.is_dir():
                        _cuda_dll_handles.append(os.add_dll_directory(str(directory)))
                        # CTranslate2 also uses native LoadLibrary, which needs PATH.
                        if str(directory) not in os.environ.get("PATH", "").split(
                            os.pathsep
                        ):
                            os.environ["PATH"] = (
                                str(directory) + os.pathsep + os.environ.get("PATH", "")
                            )
        try:
            for library in ("cublas64_12.dll", "cudnn64_9.dll"):
                _cuda_dll_handles.append(
                    ctypes.WinDLL(shutil.which(library) or library)
                )
        except OSError as error:
            raise RuntimeError(
                f"Faster Whisper CUDA 12/cuDNN 9 runtime unavailable: {error}. "
                "Install backend/requirements-faster-whisper.txt into the backend venv. "
                "A CUDA 13 toolkit alone does not provide the required CUDA 12 DLLs."
            ) from error
        _cuda_runtime_ready = True


def _release_accelerator_memory() -> None:
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


WhisperService = WhisperCppService
