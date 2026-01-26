"""Artifacts API - Endpoints for downloading generated documents."""

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.schemas.slidespec import SlideSpec
from app.services.export_service import ExportService
from app.renderers.html_slide_renderer import HTMLSlideRenderer

router = APIRouter()

# Import shared storage from runs module
from app.api.runs import _runs, _slidespecs


def make_content_disposition(filename: str, extension: str) -> str:
    """Create Content-Disposition header with proper encoding for non-ASCII filenames."""
    # ASCII fallback filename
    ascii_filename = "".join(c if c.isascii() and c.isalnum() or c in (' ', '-', '_') else '_' for c in filename)
    ascii_filename = ascii_filename.strip() or "presentation"

    # UTF-8 encoded filename (RFC 5987)
    utf8_filename = quote(filename, safe='')

    return f"attachment; filename=\"{ascii_filename}.{extension}\"; filename*=UTF-8''{utf8_filename}.{extension}"


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str):
    """Get artifact metadata."""
    if artifact_id not in _slidespecs:
        raise HTTPException(status_code=404, detail="Artifact not found")

    slidespec = _slidespecs[artifact_id]

    return {
        "artifact_id": artifact_id,
        "title": slidespec.get("deck", {}).get("title", "Untitled"),
        "slide_count": len(slidespec.get("slides", [])),
        "formats": ["pptx", "docx", "html"],
    }


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    format: Literal["pptx", "docx", "html"] = Query(default="pptx"),
):
    """Download the generated artifact in specified format."""
    if artifact_id not in _slidespecs:
        raise HTTPException(status_code=404, detail="Artifact not found")

    slidespec_dict = _slidespecs[artifact_id]
    slidespec = SlideSpec.model_validate(slidespec_dict)

    export_service = ExportService()
    renderer = HTMLSlideRenderer()

    title = slidespec.deck.title or "presentation"
    # Sanitize filename - keep alphanumeric (including Korean), spaces, hyphens, underscores
    filename = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    filename = filename[:50] or "presentation"

    if format == "pptx":
        content = export_service.export_to_pptx(slidespec)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={
                "Content-Disposition": make_content_disposition(filename, "pptx")
            },
        )

    elif format == "docx":
        content = export_service.export_to_docx(slidespec)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": make_content_disposition(filename, "docx")
            },
        )

    elif format == "html":
        html_content = renderer.render_deck(slidespec)
        return Response(
            content=html_content.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": make_content_disposition(filename, "html")
            },
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


@router.get("/artifacts/{artifact_id}/preview")
async def preview_artifact(artifact_id: str):
    """Get HTML preview of the artifact."""
    if artifact_id not in _slidespecs:
        raise HTTPException(status_code=404, detail="Artifact not found")

    slidespec_dict = _slidespecs[artifact_id]
    slidespec = SlideSpec.model_validate(slidespec_dict)

    renderer = HTMLSlideRenderer()
    html_content = renderer.render_deck(slidespec)

    return Response(
        content=html_content.encode("utf-8"),
        media_type="text/html; charset=utf-8",
    )


@router.get("/artifacts/{artifact_id}/slides/{slide_index}")
async def get_slide_html(artifact_id: str, slide_index: int):
    """Get HTML for a specific slide."""
    if artifact_id not in _slidespecs:
        raise HTTPException(status_code=404, detail="Artifact not found")

    slidespec_dict = _slidespecs[artifact_id]
    slides = slidespec_dict.get("slides", [])

    if slide_index < 0 or slide_index >= len(slides):
        raise HTTPException(status_code=404, detail="Slide not found")

    from app.schemas.slidespec import Slide
    slide = Slide.model_validate(slides[slide_index])

    renderer = HTMLSlideRenderer()
    html_content = renderer.render_slide(slide, slide_index)

    return {
        "slide_index": slide_index,
        "slide_id": slide.slide_id,
        "html": html_content,
    }


@router.get("/artifacts/{artifact_id}/slidespec")
async def get_slidespec(artifact_id: str):
    """Get the raw SlideSpec JSON."""
    if artifact_id not in _slidespecs:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return _slidespecs[artifact_id]
