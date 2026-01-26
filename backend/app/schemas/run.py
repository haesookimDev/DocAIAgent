"""Run-related Pydantic schemas."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    """Run status enumeration."""

    CREATED = "created"
    PLANNING = "planning"
    GENERATING = "generating"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DocumentType(str, Enum):
    """Output document type."""

    SLIDES = "slides"
    DOCUMENT = "document"


class RunCreate(BaseModel):
    """Request body for creating a new run."""

    prompt: str = Field(..., min_length=1, max_length=10000, description="User prompt for document generation")
    document_type: DocumentType = Field(default=DocumentType.SLIDES, description="Type of document to generate")
    language: str = Field(default="ko", max_length=20, description="Output language (BCP-47)")
    audience: str | None = Field(None, max_length=200, description="Target audience")
    tone: str | None = Field(None, max_length=200, description="Tone/style of the document")
    slide_count: int | None = Field(None, ge=1, le=100, description="Target number of slides")
    template_id: str | None = Field(None, description="Template ID to use")
    brand_kit_id: str | None = Field(None, description="Brand kit ID to use")
    options: dict[str, Any] | None = Field(None, description="Additional options")


class RunResponse(BaseModel):
    """Response for a run."""

    run_id: str
    status: RunStatus
    document_type: DocumentType
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    current_slide: int | None = None
    total_slides: int | None = None
    artifact_id: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class SSEEventType(str, Enum):
    """SSE event types."""

    # Run lifecycle
    RUN_START = "run_start"
    RUN_PROGRESS = "run_progress"
    RUN_COMPLETE = "run_complete"
    RUN_ERROR = "run_error"

    # Slide generation
    SLIDE_START = "slide_start"
    SLIDE_CHUNK = "slide_chunk"
    SLIDE_COMPLETE = "slide_complete"

    # Document generation
    SECTION_START = "section_start"
    SECTION_CHUNK = "section_chunk"
    SECTION_COMPLETE = "section_complete"


class SSEEvent(BaseModel):
    """Server-Sent Event payload."""

    event: SSEEventType
    run_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SlideChunkData(BaseModel):
    """Data for slide_chunk event."""

    slide_id: str
    slide_index: int
    html: str
    is_complete: bool = False


class RunProgressData(BaseModel):
    """Data for run_progress event."""

    status: RunStatus
    progress: float
    current_slide: int | None = None
    total_slides: int | None = None
    message: str | None = None
