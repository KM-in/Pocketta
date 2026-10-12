# Backend

The FastAPI backend provides SQLite persistence, a shared course-fair job scheduler, FFmpeg and Whisper adapters, provider-neutral structured generation, OpenAI embeddings, typed rubric grading, Markdown export, and permanent local deletion.

Always invoke Python through the repository `.venv`. Run the development server from the repository root:

```bash
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

API documentation is available locally at `http://127.0.0.1:8000/docs`.

See [model and processing configuration](../docs/FOUNDATION.md) for provider roles, usage/cost records, scheduling limits, and live smoke checks.

Course tutor, check grading, and course-scoped citation endpoints are documented in [Tutor API and validation](../docs/TUTOR.md).
