from __future__ import annotations

import sys

from ..config import Settings
from ..services.whisper import _prepare_windows_cuda_runtime


def main() -> int:
    settings = Settings()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print(
            "Faster Whisper package missing.\n"
            "Run: python -m pip install -r backend/requirements-faster-whisper.txt",
            file=sys.stderr,
        )
        return 1

    model_ref = (
        str(settings.faster_whisper_model_path)
        if settings.faster_whisper_model_path
        else settings.faster_whisper_model_name
    )
    print(f"Preparing Faster Whisper model: {model_ref}")
    print("This command may download the model if it is not already available locally.")
    try:
        _prepare_windows_cuda_runtime()
        WhisperModel(
            model_ref,
            device="cuda",
            compute_type=settings.faster_whisper_compute_type,
        )
    except (RuntimeError, OSError, ValueError) as error:
        print(
            "Could not prepare Faster Whisper for CUDA.\n"
            f"Error: {error}\n"
            "Check NVIDIA drivers plus CUDA cuBLAS/cuDNN runtime libraries. "
            "If you already have a local CTranslate2 model directory, set FASTER_WHISPER_MODEL_PATH in .env.",
            file=sys.stderr,
        )
        return 1
    print("Faster Whisper CUDA model is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
