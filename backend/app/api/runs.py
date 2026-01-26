"""Runs API - Endpoints for creating and streaming document generation runs."""

import asyncio
import json
import uuid
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.schemas.run import (
    RunCreate,
    RunResponse,
    RunStatus,
    DocumentType,
    SSEEvent,
    SSEEventType,
)
from app.services.agent_service import AgentService, get_agent_service
from app.services.export_service import ExportService
from app.services.storage_service import get_storage_service

router = APIRouter()


def _get_storage():
    """Get storage service instance."""
    return get_storage_service()


# Export for backward compatibility with artifacts.py
def get_runs_storage() -> dict[str, dict]:
    """Get runs storage (for internal use by other modules)."""
    return _get_storage().get_all_runs()


def get_slidespecs_storage() -> dict[str, dict]:
    """Get slidespecs storage (for internal use by other modules)."""
    return _get_storage().get_all_slidespecs()


# Legacy names for artifacts.py compatibility
_runs = property(lambda self: get_runs_storage())
_slidespecs = property(lambda self: get_slidespecs_storage())


@router.post("/runs", response_model=RunResponse)
async def create_run(request: RunCreate):
    """Create a new document generation run."""
    storage = _get_storage()
    run_id = str(uuid.uuid4())
    now = datetime.utcnow()

    run_data = {
        "run_id": run_id,
        "status": RunStatus.CREATED,
        "document_type": request.document_type,
        "progress": 0.0,
        "current_slide": None,
        "total_slides": None,
        "artifact_id": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "request": request.model_dump(),
    }

    storage.save_run(run_id, run_data)

    return RunResponse(**run_data)


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    """Get the status of a run."""
    storage = _get_storage()
    run_data = storage.get_run(run_id)

    if not run_data:
        raise HTTPException(status_code=404, detail="Run not found")

    return RunResponse(**run_data)


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str):
    """Stream run events using Server-Sent Events.

    This endpoint starts the generation process and streams real-time updates
    including slide HTML as it's generated.
    """
    storage = _get_storage()
    run_data = storage.get_run(run_id)

    if not run_data:
        raise HTTPException(status_code=404, detail="Run not found")

    request = RunCreate(**run_data["request"])

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events."""
        try:
            agent_service = get_agent_service()

            # Update run status
            run_data["status"] = RunStatus.PLANNING
            run_data["updated_at"] = datetime.utcnow()
            storage.save_run(run_id, run_data)

            async for event in agent_service.generate_slides_stream(
                prompt=request.prompt,
                language=request.language,
                audience=request.audience,
                tone=request.tone,
                slide_count=request.slide_count,
            ):
                # Update run data based on event
                if event.event == SSEEventType.RUN_PROGRESS:
                    status_value = event.data.get("status", "generating")
                    try:
                        run_data["status"] = RunStatus(status_value) if isinstance(status_value, str) else status_value
                    except ValueError:
                        run_data["status"] = RunStatus.GENERATING
                    run_data["progress"] = event.data.get("progress", 0)
                    run_data["current_slide"] = event.data.get("current_slide")
                    run_data["total_slides"] = event.data.get("total_slides")
                    run_data["updated_at"] = datetime.utcnow()
                    storage.save_run(run_id, run_data)

                elif event.event == SSEEventType.RUN_COMPLETE:
                    run_data["status"] = RunStatus.COMPLETED
                    run_data["progress"] = 100.0
                    run_data["updated_at"] = datetime.utcnow()

                    # Store slidespec
                    if "slidespec" in event.data:
                        slidespec_data = event.data["slidespec"]
                        slidespec_data["created_at"] = datetime.utcnow().isoformat()
                        storage.save_slidespec(run_id, slidespec_data)
                        run_data["artifact_id"] = run_id

                    storage.save_run(run_id, run_data)

                elif event.event == SSEEventType.RUN_ERROR:
                    run_data["status"] = RunStatus.FAILED
                    run_data["error"] = event.data.get("error")
                    run_data["updated_at"] = datetime.utcnow()
                    storage.save_run(run_id, run_data)

                # Yield event as SSE format
                yield {
                    "event": event.event.value,
                    "id": str(uuid.uuid4()),
                    "data": json.dumps(event.data, default=str),
                }

        except Exception as e:
            run_data["status"] = RunStatus.FAILED
            run_data["error"] = str(e)
            run_data["updated_at"] = datetime.utcnow()
            storage.save_run(run_id, run_data)

            error_event = {
                "event": SSEEventType.RUN_ERROR.value,
                "id": str(uuid.uuid4()),
                "data": json.dumps({"error": str(e)}),
            }
            yield error_event

    return EventSourceResponse(event_generator())


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    """Cancel a running generation."""
    storage = _get_storage()
    run_data = storage.get_run(run_id)

    if not run_data:
        raise HTTPException(status_code=404, detail="Run not found")

    if run_data["status"] in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Run cannot be cancelled")

    run_data["status"] = RunStatus.CANCELLED
    run_data["updated_at"] = datetime.utcnow()
    storage.save_run(run_id, run_data)

    return {"message": "Run cancelled", "run_id": run_id}


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str):
    """Delete a run and its associated artifact."""
    storage = _get_storage()
    run_data = storage.get_run(run_id)

    if not run_data:
        raise HTTPException(status_code=404, detail="Run not found")

    # Delete associated slidespec if exists
    if run_data.get("artifact_id"):
        storage.delete_slidespec(run_data["artifact_id"])

    storage.delete_run(run_id)

    return {"message": "Run deleted", "run_id": run_id}


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List all runs."""
    storage = _get_storage()
    runs, total = storage.list_runs(limit=limit, offset=offset)

    return {
        "items": [RunResponse(**r) for r in runs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# Helper endpoint for quick testing without SSE
@router.post("/runs/generate-sync")
async def generate_sync(request: RunCreate):
    """Synchronously generate slides (for testing, not recommended for production)."""
    storage = _get_storage()
    run_id = str(uuid.uuid4())
    now = datetime.utcnow()

    run_data = {
        "run_id": run_id,
        "status": RunStatus.GENERATING,
        "document_type": request.document_type,
        "progress": 0.0,
        "current_slide": None,
        "total_slides": None,
        "artifact_id": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "request": request.model_dump(),
    }
    storage.save_run(run_id, run_data)

    try:
        agent_service = get_agent_service()
        slidespec = await agent_service.generate_slidespec(
            prompt=request.prompt,
            language=request.language,
            audience=request.audience,
            tone=request.tone,
            slide_count=request.slide_count,
        )

        slidespec_data = slidespec.model_dump()
        slidespec_data["created_at"] = now.isoformat()
        storage.save_slidespec(run_id, slidespec_data)

        run_data["status"] = RunStatus.COMPLETED
        run_data["progress"] = 100.0
        run_data["artifact_id"] = run_id
        run_data["total_slides"] = len(slidespec.slides)
        run_data["updated_at"] = datetime.utcnow()
        storage.save_run(run_id, run_data)

        return {
            "run": RunResponse(**run_data),
            "slidespec": slidespec.model_dump(),
        }

    except Exception as e:
        run_data["status"] = RunStatus.FAILED
        run_data["error"] = str(e)
        run_data["updated_at"] = datetime.utcnow()
        storage.save_run(run_id, run_data)
        raise HTTPException(status_code=500, detail=str(e))
