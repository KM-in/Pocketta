# Test fixtures

Only synthetic, self-recorded with consent, or appropriately licensed fixtures may be added here. Record provenance and consent or licence details beside every audio fixture.

## Local Whisper integration fixture

`transcription/lecture.mp4` is a short synthetic lecture video with a black video track and speech created locally with macOS `say` using the Samantha voice at rate 180. The spoken text is “A process is a program in execution. Each thread has its own stack and registers.” It contains no personal recording. The optional integration test uploads it through the recording API, extracts and normalizes its audio with FFmpeg, transcribes it with the configured local whisper.cpp binary and model, and checks that the transcript is persisted and readable through the API. It skips when the local Whisper model is not prepared.

Run the integration test after preparing the local `base.en` model and whisper.cpp binary:

```sh
POCKETTA_TEST_WHISPER_MODEL=/path/to/ggml-base.en.bin \
POCKETTA_TEST_WHISPER_CLI=/path/to/whisper-cli \
.venv/bin/python -m pytest backend/tests/test_transcription_integration.py -q
```

It makes no cloud transcription, text-generation, vision, or embedding requests.

The same test also covers Faster Whisper when its CUDA runtime and a local model are prepared. Tests ignore `.env`; pass model settings explicitly using `POCKETTA_TEST_FASTER_WHISPER_MODEL`, `POCKETTA_TEST_FASTER_WHISPER_MODEL_NAME`, and `POCKETTA_TEST_FASTER_WHISPER_COMPUTE_TYPE`. For example, on Windows:

```powershell
$env:POCKETTA_TEST_FASTER_WHISPER_MODEL = 'D:/models/whisper-ct2'
$env:POCKETTA_TEST_FASTER_WHISPER_COMPUTE_TYPE = 'int8'
.venv/Scripts/python.exe -m pytest backend/tests/test_transcription_integration.py -q
```
