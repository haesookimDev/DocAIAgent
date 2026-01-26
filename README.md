# DocAIAgent

DocAIAgent is a work-grade AI document generation platform focused on business
slides and docs. This repo combines a FastAPI backend prototype with
versioned specifications for IR, workflows, and layout presets.

## What is in this repo

- `backend/`: FastAPI app for run orchestration, SSE streaming, HTML preview,
  and PPTX/DOCX export.
- `specs/`: JSON Schemas, workflow specs, layout presets, examples, and
  validation tooling.
- `architecture.md`, `documents.md`, `guideline*.md`: product and system
  design notes.
- `endpoint_spec.md`: draft API contract (v1).

## Quick start (backend)

1. Install deps:
   `pip install -r backend/requirements.txt`
2. Configure env:
   `cp backend/.env.example backend/.env`
3. Run:
   `python -m app.main` (from `backend/`)
   or
   `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
4. Open:
   - UI: `http://localhost:8000/static/index.html`
   - API docs: `http://localhost:8000/docs`
   - Health: `http://localhost:8000/health`

More details: `backend/README.md`

## Specs

- Validation (python):
  `python specs/tooling/python/validate_schemas.py`
  `python specs/tooling/python/validate_examples.py`
- Optional TS types:
  `cd specs/tooling/node && npm install && npm run gen:types`

See `specs/README.md` for versioning rules and details.

## Concepts

- IR first: SlideSpec/DocSpec are the contract between LLM output and renderers.
- Deterministic layout: layout presets + layout plans support QC and fix loops.
- Artifacts: PPTX/DOCX/PDF outputs plus previews and reports.

## Status

Early-stage prototype + specs. APIs and schemas may change.
