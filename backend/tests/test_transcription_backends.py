from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.config import Settings
from backend.app.services.processes import ProcessRegistry
from backend.app.services.whisper import (
    FasterWhisperService,
    Readiness,
    TranscriptionService,
    _prepare_windows_cuda_runtime,
    faster_whisper_readiness,
    transcript_from_faster_whisper,
)


@pytest.fixture(autouse=True)
def isolate_optional_runtime(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.whisper._prepare_windows_cuda_runtime", lambda: None
    )
    monkeypatch.setattr("importlib.metadata.version", lambda package: "18.1.0")


def test_faster_whisper_segments_match_transcript_contract() -> None:
    result = transcript_from_faster_whisper(
        [
            SimpleNamespace(
                start=0.0,
                end=1.25,
                text="Clear CUDA segment",
                words=[
                    SimpleNamespace(probability=0.9),
                    SimpleNamespace(probability=0.8),
                ],
            ),
            SimpleNamespace(
                start=1.25,
                end=2.0,
                text="Uncertain CUDA segment",
                avg_logprob=-1.5,
            ),
        ],
        duration_ms=2000,
        threshold=0.6,
    )

    assert [segment.id for segment in result.segments] == ["seg-0001", "seg-0002"]
    assert result.segments[0].start_ms == 0
    assert result.segments[0].end_ms == 1250
    assert result.segments[0].uncertain is False
    assert result.segments[1].uncertain is True


def test_faster_whisper_timestamps_stay_within_recording():
    result = transcript_from_faster_whisper(
        [SimpleNamespace(start=30, end=43, text="Final segment")],
        duration_ms=39552,
        threshold=0.6,
    )
    assert result.segments[0].start_ms == 30000
    assert result.segments[0].end_ms == 39552


def test_auto_backend_prefers_ready_faster_whisper(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.whisper.faster_whisper_readiness",
        lambda settings: Readiness(True, "ready"),
    )
    service = TranscriptionService(Settings(_env_file=None), ProcessRegistry())
    assert service.selected_backend() == "faster_whisper"


def test_auto_backend_falls_back_to_whisper_cpp(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.whisper.faster_whisper_readiness",
        lambda settings: Readiness(False, "not ready"),
    )
    service = TranscriptionService(Settings(_env_file=None), ProcessRegistry())
    assert service.selected_backend() == "whisper_cpp"


def test_explicit_faster_whisper_does_not_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.whisper.faster_whisper_readiness",
        lambda settings: Readiness(False, "not ready"),
    )
    service = TranscriptionService(
        Settings(transcription_backend="faster_whisper"), ProcessRegistry()
    )
    assert service.selected_backend() == "faster_whisper"


def test_faster_whisper_uses_batched_inference_pipeline(monkeypatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        "backend.app.services.whisper._faster_whisper_model_directory",
        lambda settings: Path("prepared-turbo"),
    )

    class FakeWhisperModel:
        def __init__(
            self, model_ref: str, device: str, compute_type: str, local_files_only: bool
        ) -> None:
            calls["model_ref"] = model_ref
            calls["device"] = device
            calls["compute_type"] = compute_type
            calls["local_files_only"] = local_files_only

    class FakeBatchedInferencePipeline:
        def __init__(self, model: FakeWhisperModel) -> None:
            calls["pipeline_model"] = model

        def transcribe(self, audio: str, **kwargs: object):
            calls["audio"] = audio
            calls["kwargs"] = kwargs
            return [
                SimpleNamespace(start=0.0, end=1.0, text="Batched segment")
            ], SimpleNamespace()

    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        SimpleNamespace(
            WhisperModel=FakeWhisperModel,
            BatchedInferencePipeline=FakeBatchedInferencePipeline,
        ),
    )

    service = FasterWhisperService(
        Settings(
            _env_file=None,
            faster_whisper_model_name="turbo",
            faster_whisper_model_path=None,
            faster_whisper_compute_type="int8",
            faster_whisper_batch_size=8,
            faster_whisper_vad_filter=True,
        )
    )
    result = service.transcribe("lecture", Path("audio.wav"), 1000)

    assert service._pipeline is None
    assert result.segments[0].text == "Batched segment"
    assert calls["model_ref"] == "prepared-turbo"
    assert calls["device"] == "cuda"
    assert calls["compute_type"] == "int8"
    assert calls["local_files_only"] is True
    assert calls["audio"] == "audio.wav"
    assert calls["kwargs"] == {
        "beam_size": 5,
        "batch_size": 8,
        "language": "en",
        "vad_filter": True,
    }


@pytest.mark.parametrize("lazy", [False, True])
def test_faster_whisper_unloads_pipeline_after_transcription_failure(
    monkeypatch,
    lazy: bool,
) -> None:
    monkeypatch.setattr(
        "backend.app.services.whisper._faster_whisper_model_directory",
        lambda settings: Path("prepared-turbo"),
    )

    class FakeWhisperModel:
        def __init__(
            self, model_ref: str, device: str, compute_type: str, local_files_only: bool
        ) -> None:
            pass

    class FakeBatchedInferencePipeline:
        def __init__(self, model: FakeWhisperModel) -> None:
            pass

        def transcribe(self, audio: str, **kwargs: object):
            if lazy:

                def segments():
                    raise RuntimeError("transcription failed")
                    yield  # pragma: no cover

                return segments(), SimpleNamespace()
            raise RuntimeError("transcription failed")

    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        SimpleNamespace(
            WhisperModel=FakeWhisperModel,
            BatchedInferencePipeline=FakeBatchedInferencePipeline,
        ),
    )

    service = FasterWhisperService(Settings(_env_file=None))

    with pytest.raises(RuntimeError, match="transcription failed"):
        service.transcribe("lecture", Path("audio.wav"), 1000)

    assert service._pipeline is None


def test_faster_whisper_readiness_accepts_local_model_path(
    tmp_path: Path, monkeypatch
) -> None:
    model_dir = tmp_path / "turbo-ct2"
    model_dir.mkdir()
    for filename in ("model.bin", "config.json", "tokenizer.json"):
        (model_dir / filename).write_text("{}")
    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        SimpleNamespace(),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "ctranslate2",
        SimpleNamespace(get_cuda_device_count=lambda: 1),
    )

    readiness = faster_whisper_readiness(Settings(faster_whisper_model_path=model_dir))

    assert readiness.ready is True
    assert str(model_dir) in readiness.detail


def test_vad_disabled_uses_standard_inference_for_long_recordings(monkeypatch):
    calls = {}

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, audio, **kwargs):
            calls.update(kwargs)
            return iter([SimpleNamespace(start=30, end=60, text="Long lecture")]), None

    def unexpected_batch(**kwargs):
        pytest.fail("VAD-disabled recordings must use standard inference")

    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=Model, BatchedInferencePipeline=unexpected_batch),
    )
    monkeypatch.setattr(
        "backend.app.services.whisper._faster_whisper_model_directory",
        lambda settings: Path("local"),
    )
    service = FasterWhisperService(
        Settings(_env_file=None, faster_whisper_vad_filter=False)
    )
    result = service.transcribe("lecture", Path("audio.wav"), 60000)
    assert result.segments[0].end_ms == 60000
    assert calls["vad_filter"] is False
    assert "batch_size" not in calls
    assert service._pipeline is None


@pytest.mark.parametrize("missing", ["config.json", "model.bin", "tokenizer.json"])
def test_readiness_rejects_incomplete_local_model(tmp_path, monkeypatch, missing):
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "ctranslate2",
        SimpleNamespace(get_cuda_device_count=lambda: 1),
    )
    for name in ("config.json", "model.bin", "tokenizer.json"):
        if name != missing:
            (tmp_path / name).write_text("{}")
    result = faster_whisper_readiness(
        Settings(_env_file=None, faster_whisper_model_path=tmp_path)
    )
    assert result.ready is False
    assert missing in result.detail


def test_readiness_resolves_turbo_using_offline_faster_whisper_mapping(
    tmp_path, monkeypatch
):
    calls = []

    def download_model(name, **kwargs):
        calls.append((name, kwargs))
        return str(tmp_path)

    for name in ("config.json", "model.bin", "tokenizer.json"):
        (tmp_path / name).write_text("{}")
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper.utils",
        SimpleNamespace(download_model=download_model),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "ctranslate2",
        SimpleNamespace(get_cuda_device_count=lambda: 1),
    )
    result = faster_whisper_readiness(Settings(_env_file=None))
    assert result.ready is True
    assert calls == [("turbo", {"local_files_only": True})]


def test_readiness_reports_incompatible_pyav(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", SimpleNamespace())
    monkeypatch.setitem(__import__("sys").modules, "ctranslate2", SimpleNamespace())
    monkeypatch.setattr("importlib.metadata.version", lambda package: "19.0.1")
    result = faster_whisper_readiness(Settings(_env_file=None))
    assert result.ready is False
    assert "av<19" in result.detail


def test_windows_runtime_registers_and_keeps_wheel_dll_directories(
    tmp_path, monkeypatch
):
    import ctypes
    import os

    from backend.app.services import whisper

    registered = []
    loaded = []
    handles = []
    for package in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
        (tmp_path / package / "bin").mkdir(parents=True)
    monkeypatch.setattr(whisper, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(whisper, "_cuda_runtime_ready", False)
    monkeypatch.setattr(whisper, "_cuda_dll_handles", handles)
    monkeypatch.setattr(
        "importlib.util.find_spec",
        lambda name: SimpleNamespace(submodule_search_locations=[str(tmp_path)]),
    )
    monkeypatch.setattr(
        os,
        "add_dll_directory",
        lambda path: registered.append(path) or object(),
        raising=False,
    )
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda path: loaded.append(Path(path).name) or object(),
        raising=False,
    )
    monkeypatch.setattr(whisper.shutil, "which", lambda library: None)
    monkeypatch.setenv("PATH", "")
    _prepare_windows_cuda_runtime()
    _prepare_windows_cuda_runtime()
    assert len(registered) == 4
    assert loaded == ["cublas64_12.dll", "cudnn64_9.dll"]
    assert len(handles) == 6
    assert all(path in os.environ["PATH"].split(os.pathsep) for path in registered)


def test_concurrent_lectures_do_not_share_or_duplicate_gpu_pipeline(monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor

    active = 0
    peak = 0
    service = FasterWhisperService(Settings(_env_file=None))

    class Pipeline:
        def transcribe(self, *args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            time.sleep(0.03)
            active -= 1
            return [SimpleNamespace(start=0, end=1, text="Lecture")], None

    monkeypatch.setattr(service, "_load_pipeline", Pipeline)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(
                lambda lecture: service.transcribe(lecture, Path("audio.wav"), 1000),
                ["one", "two"],
            )
        )
    assert len(results) == 2
    assert peak == 1
    assert service._pipeline is None


@pytest.mark.parametrize(
    "field", ["faster_whisper_beam_size", "faster_whisper_batch_size"]
)
def test_inference_sizes_must_be_positive(field):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: 0})
