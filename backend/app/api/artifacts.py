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
        # Use image-based export for pixel-perfect rendering
        content = await export_service.export_to_pptx_as_images(slidespec)
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


@router.put("/artifacts/{artifact_id}/slides/{slide_index}")
async def update_slide(artifact_id: str, slide_index: int, slide_data: dict):
    """Update a specific slide's data."""
    if artifact_id not in _slidespecs:
        raise HTTPException(status_code=404, detail="Artifact not found")

    slidespec_dict = _slidespecs[artifact_id]
    slides = slidespec_dict.get("slides", [])

    if slide_index < 0 or slide_index >= len(slides):
        raise HTTPException(status_code=404, detail="Slide not found")

    # Validate the new slide data
    from app.schemas.slidespec import Slide
    try:
        validated_slide = Slide.model_validate(slide_data)
        # Update the slide in storage
        slides[slide_index] = validated_slide.model_dump()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid slide data: {str(e)}")

    # Re-render the slide HTML
    renderer = HTMLSlideRenderer()
    html_content = renderer.render_slide(validated_slide, slide_index)

    return {
        "slide_index": slide_index,
        "slide_id": validated_slide.slide_id,
        "html": html_content,
        "message": "Slide updated successfully",
    }


@router.put("/artifacts/{artifact_id}/slides/{slide_index}/element/{element_id}")
async def update_element(artifact_id: str, slide_index: int, element_id: str, element_data: dict):
    """Update a specific element within a slide."""
    if artifact_id not in _slidespecs:
        raise HTTPException(status_code=404, detail="Artifact not found")

    slidespec_dict = _slidespecs[artifact_id]
    slides = slidespec_dict.get("slides", [])

    if slide_index < 0 or slide_index >= len(slides):
        raise HTTPException(status_code=404, detail="Slide not found")

    slide = slides[slide_index]
    elements = slide.get("elements", [])

    # Find and update the element
    element_found = False
    for i, elem in enumerate(elements):
        if elem.get("element_id") == element_id:
            # Merge the update with existing element
            elements[i].update(element_data)
            element_found = True
            break

    if not element_found:
        raise HTTPException(status_code=404, detail=f"Element {element_id} not found")

    # Re-render the slide
    from app.schemas.slidespec import Slide
    validated_slide = Slide.model_validate(slide)
    renderer = HTMLSlideRenderer()
    html_content = renderer.render_slide(validated_slide, slide_index)

    return {
        "slide_index": slide_index,
        "element_id": element_id,
        "html": html_content,
        "message": "Element updated successfully",
    }


@router.post("/artifacts/{artifact_id}/slides/{slide_index}/regenerate")
async def regenerate_slide(artifact_id: str, slide_index: int, prompt: str = None):
    """Regenerate a specific slide with optional new prompt."""
    if artifact_id not in _slidespecs:
        raise HTTPException(status_code=404, detail="Artifact not found")

    slidespec_dict = _slidespecs[artifact_id]
    slides = slidespec_dict.get("slides", [])

    if slide_index < 0 or slide_index >= len(slides):
        raise HTTPException(status_code=404, detail="Slide not found")

    # Get the current slide info
    current_slide = slides[slide_index]

    # Use agent service to regenerate this slide
    from app.services.agent_service import get_agent_service

    agent = get_agent_service()

    slide_info = {
        "type": current_slide.get("type", "content"),
        "title": current_slide.get("title") or (
            next((e.get("content", {}).get("text", "") for e in current_slide.get("elements", []) if e.get("role") == "title"), "")
        ),
        "key_points": prompt.split(",") if prompt else ["Regenerate with improvements"],
    }

    presentation_context = {
        "title": slidespec_dict.get("deck", {}).get("title", "Presentation"),
        "audience": slidespec_dict.get("deck", {}).get("audience", "General"),
        "tone": slidespec_dict.get("deck", {}).get("tone", "Professional"),
        "total_slides": len(slides),
    }

    language = slidespec_dict.get("deck", {}).get("language", "ko")

    # Generate new slide
    new_slide_dict = await agent.generate_single_slide(
        slide_index, slide_info, presentation_context, language
    )

    # Update storage
    slides[slide_index] = new_slide_dict

    # Render HTML
    from app.schemas.slidespec import Slide
    validated_slide = Slide.model_validate(new_slide_dict)
    renderer = HTMLSlideRenderer()
    html_content = renderer.render_slide(validated_slide, slide_index)

    return {
        "slide_index": slide_index,
        "slide_id": validated_slide.slide_id,
        "html": html_content,
        "slide_data": new_slide_dict,
        "message": "Slide regenerated successfully",
    }
