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

router = APIRouter()

# In-memory storage for MVP (replace with database later)
_runs: dict[str, dict] = {}
_slidespecs: dict[str, dict] = {}


@router.post("/runs", response_model=RunResponse)
async def create_run(request: RunCreate):
    """Create a new document generation run."""
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

    _runs[run_id] = run_data

    return RunResponse(**run_data)


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    """Get the status of a run."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Run not found")

    return RunResponse(**_runs[run_id])


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str):
    """Stream run events using Server-Sent Events.

    This endpoint starts the generation process and streams real-time updates
    including slide HTML as it's generated.
    """
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Run not found")

    run_data = _runs[run_id]
    request = RunCreate(**run_data["request"])

    async def event_generator() -> AsyncGenerator[dict, None]:
        """Generate SSE events."""
        try:
            agent_service = get_agent_service()

            # Update run status
            run_data["status"] = RunStatus.PLANNING
            run_data["updated_at"] = datetime.utcnow()

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

                elif event.event == SSEEventType.RUN_COMPLETE:
                    run_data["status"] = RunStatus.COMPLETED
                    run_data["progress"] = 100.0
                    run_data["updated_at"] = datetime.utcnow()

                    # Store slidespec
                    if "slidespec" in event.data:
                        _slidespecs[run_id] = event.data["slidespec"]
                        run_data["artifact_id"] = run_id  # Use run_id as artifact_id for MVP

                elif event.event == SSEEventType.RUN_ERROR:
                    run_data["status"] = RunStatus.FAILED
                    run_data["error"] = event.data.get("error")
                    run_data["updated_at"] = datetime.utcnow()

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
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Run not found")

    run_data = _runs[run_id]

    if run_data["status"] in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Run cannot be cancelled")

    run_data["status"] = RunStatus.CANCELLED
    run_data["updated_at"] = datetime.utcnow()

    return {"message": "Run cancelled", "run_id": run_id}


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List all runs."""
    runs = list(_runs.values())
    runs.sort(key=lambda x: x["created_at"], reverse=True)

    return {
        "items": [RunResponse(**r) for r in runs[offset:offset + limit]],
        "total": len(runs),
        "limit": limit,
        "offset": offset,
    }


# Helper endpoint for quick testing without SSE
@router.post("/runs/generate-sync")
async def generate_sync(request: RunCreate):
    """Synchronously generate slides (for testing, not recommended for production)."""
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
    _runs[run_id] = run_data

    try:
        agent_service = get_agent_service()
        slidespec = await agent_service.generate_slidespec(
            prompt=request.prompt,
            language=request.language,
            audience=request.audience,
            tone=request.tone,
            slide_count=request.slide_count,
        )

        _slidespecs[run_id] = slidespec.model_dump()
        run_data["status"] = RunStatus.COMPLETED
        run_data["progress"] = 100.0
        run_data["artifact_id"] = run_id
        run_data["total_slides"] = len(slidespec.slides)
        run_data["updated_at"] = datetime.utcnow()

        return {
            "run": RunResponse(**run_data),
            "slidespec": slidespec.model_dump(),
        }

    except Exception as e:
        run_data["status"] = RunStatus.FAILED
        run_data["error"] = str(e)
        run_data["updated_at"] = datetime.utcnow()
        raise HTTPException(status_code=500, detail=str(e))
