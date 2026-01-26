"""Agent Service - Orchestrates slide/document generation with LLM."""

import json
import uuid
from datetime import datetime
from typing import AsyncGenerator, Callable, Any

from app.services.llm_service import LLMService, get_llm_service
from app.renderers.html_slide_renderer import HTMLSlideRenderer
from app.schemas.slidespec import SlideSpec
from app.schemas.run import SSEEvent, SSEEventType, RunStatus


# System prompts for different stages
OUTLINE_SYSTEM_PROMPT = """You are an expert presentation consultant who creates well-structured slide outlines.
Given a user's request, create a clear, logical outline for a presentation.

Output your response as valid JSON in this format:
{
  "title": "Presentation Title",
  "sections": [
    {
      "section_id": "sec1",
      "title": "Section Title",
      "slides": 2,
      "key_points": ["point 1", "point 2"]
    }
  ]
}

Rules:
- Create 4-7 sections
- Each section should have 1-4 slides
- Total slides should match the requested count if specified
- First section should be an executive summary
- Last section should be conclusion/next steps
- Output ONLY valid JSON, no explanations"""

SLIDESPEC_SYSTEM_PROMPT = """You are a presentation content generator that creates detailed slide specifications.
Given an outline and requirements, generate a complete SlideSpec JSON.

The output must be a valid SlideSpec JSON following this structure:
{
  "schema_version": "slidespec_v1",
  "deck": {
    "title": "string",
    "subtitle": "optional string",
    "language": "ko",
    "audience": "optional string",
    "tone": "optional string"
  },
  "slides": [
    {
      "slide_id": "s1",
      "type": "title|section|content|closing",
      "layout": {"layout_id": "layout_name"},
      "elements": [
        {
          "element_id": "s1_e1",
          "kind": "text|bullets|image|chart|table",
          "role": "title|subtitle|body|visual",
          "content": {...}
        }
      ],
      "speaker_notes": "optional"
    }
  ]
}

Available layout_ids:
- title_center: Title slides with centered text
- section_header: Section divider slides
- one_column: Single column content
- two_column: Two column layout
- chart_focus: Chart with key insights
- table_focus: Table-focused layout
- quote_center: Quote/highlight
- closing: Thank you/closing slides

Element content formats:
- text: {"text": "content"}
- bullets: {"items": ["item1", "item2"]}
- table: {"columns": ["A", "B"], "rows": [["a1", "b1"]]}
- chart: {"chart_type": "bar|line|pie", "title": "...", "series": [{"name": "...", "data": [{"x": "...", "y": 10}]}]}
- image: {"alt_text": "description", "caption": "optional"}

Rules:
- slide_id format: s1, s2, s3...
- element_id format: s1_e1, s1_e2...
- Keep bullet points concise (max 8 per slide)
- Use appropriate layouts for content type
- Add speaker notes with key talking points
- Output ONLY valid JSON"""


class AgentService:
    """Service for generating presentations using LLM."""

    def __init__(self, llm_service: LLMService | None = None):
        self.llm = llm_service or get_llm_service()
        self.renderer = HTMLSlideRenderer()

    async def generate_outline(
        self,
        prompt: str,
        language: str = "ko",
        audience: str | None = None,
        tone: str | None = None,
        slide_count: int | None = None,
    ) -> dict:
        """Generate a presentation outline."""
        user_prompt = f"""Create a presentation outline for:
{prompt}

Requirements:
- Language: {language}
- Target audience: {audience or 'General'}
- Tone: {tone or 'Professional'}
- Target slide count: {slide_count or '10-15'} slides

Create a well-structured outline."""

        result = await self.llm.generate_json(user_prompt, OUTLINE_SYSTEM_PROMPT)
        return result

    async def generate_slidespec(
        self,
        prompt: str,
        outline: dict | None = None,
        language: str = "ko",
        audience: str | None = None,
        tone: str | None = None,
        slide_count: int | None = None,
    ) -> SlideSpec:
        """Generate a complete SlideSpec from prompt and optional outline."""
        # Build the user prompt
        outline_text = ""
        if outline:
            outline_text = f"\n\nOutline to follow:\n{json.dumps(outline, ensure_ascii=False, indent=2)}"

        user_prompt = f"""Create a complete presentation for:
{prompt}

Requirements:
- Language: {language}
- Target audience: {audience or 'General'}
- Tone: {tone or 'Professional'}
- Target slide count: {slide_count or 10} slides
{outline_text}

Generate the complete SlideSpec JSON."""

        result = await self.llm.generate_json(user_prompt, SLIDESPEC_SYSTEM_PROMPT)

        # Validate and return as SlideSpec
        return SlideSpec.model_validate(result)

    async def generate_slides_stream(
        self,
        prompt: str,
        language: str = "ko",
        audience: str | None = None,
        tone: str | None = None,
        slide_count: int | None = None,
        on_event: Callable[[SSEEvent], Any] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Generate slides with real-time streaming updates.

        Yields SSEEvent objects for each stage of generation.
        """
        run_id = str(uuid.uuid4())

        # Start event
        start_event = SSEEvent(
            event=SSEEventType.RUN_START,
            run_id=run_id,
            data={"message": "Starting presentation generation..."},
        )
        if on_event:
            await on_event(start_event)
        yield start_event

        try:
            # Generate outline first
            progress_event = SSEEvent(
                event=SSEEventType.RUN_PROGRESS,
                run_id=run_id,
                data={
                    "status": RunStatus.PLANNING.value,
                    "progress": 10.0,
                    "message": "Generating outline...",
                },
            )
            if on_event:
                await on_event(progress_event)
            yield progress_event

            outline = await self.generate_outline(
                prompt, language, audience, tone, slide_count
            )

            # Generate SlideSpec
            progress_event = SSEEvent(
                event=SSEEventType.RUN_PROGRESS,
                run_id=run_id,
                data={
                    "status": RunStatus.GENERATING.value,
                    "progress": 30.0,
                    "message": "Generating slides...",
                },
            )
            if on_event:
                await on_event(progress_event)
            yield progress_event

            slidespec = await self.generate_slidespec(
                prompt, outline, language, audience, tone, slide_count
            )

            total_slides = len(slidespec.slides)

            # Render each slide and emit events
            progress_event = SSEEvent(
                event=SSEEventType.RUN_PROGRESS,
                run_id=run_id,
                data={
                    "status": RunStatus.RENDERING.value,
                    "progress": 50.0,
                    "message": "Rendering slides...",
                    "total_slides": total_slides,
                },
            )
            if on_event:
                await on_event(progress_event)
            yield progress_event

            for idx, slide in enumerate(slidespec.slides):
                # Slide start
                slide_start_event = SSEEvent(
                    event=SSEEventType.SLIDE_START,
                    run_id=run_id,
                    data={
                        "slide_id": slide.slide_id,
                        "slide_index": idx,
                        "total_slides": total_slides,
                    },
                )
                if on_event:
                    await on_event(slide_start_event)
                yield slide_start_event

                # Render slide HTML
                html = self.renderer.render_slide(slide, idx)

                # Slide chunk (complete HTML for this slide)
                slide_chunk_event = SSEEvent(
                    event=SSEEventType.SLIDE_CHUNK,
                    run_id=run_id,
                    data={
                        "slide_id": slide.slide_id,
                        "slide_index": idx,
                        "html": html,
                        "is_complete": True,
                    },
                )
                if on_event:
                    await on_event(slide_chunk_event)
                yield slide_chunk_event

                # Slide complete
                slide_complete_event = SSEEvent(
                    event=SSEEventType.SLIDE_COMPLETE,
                    run_id=run_id,
                    data={
                        "slide_id": slide.slide_id,
                        "slide_index": idx,
                    },
                )
                if on_event:
                    await on_event(slide_complete_event)
                yield slide_complete_event

                # Update progress
                progress = 50.0 + (idx + 1) / total_slides * 45.0
                progress_event = SSEEvent(
                    event=SSEEventType.RUN_PROGRESS,
                    run_id=run_id,
                    data={
                        "status": RunStatus.RENDERING.value,
                        "progress": progress,
                        "current_slide": idx + 1,
                        "total_slides": total_slides,
                    },
                )
                if on_event:
                    await on_event(progress_event)
                yield progress_event

            # Complete event
            complete_event = SSEEvent(
                event=SSEEventType.RUN_COMPLETE,
                run_id=run_id,
                data={
                    "status": RunStatus.COMPLETED.value,
                    "progress": 100.0,
                    "total_slides": total_slides,
                    "slidespec": slidespec.model_dump(),
                },
            )
            if on_event:
                await on_event(complete_event)
            yield complete_event

        except Exception as e:
            error_event = SSEEvent(
                event=SSEEventType.RUN_ERROR,
                run_id=run_id,
                data={
                    "status": RunStatus.FAILED.value,
                    "error": str(e),
                },
            )
            if on_event:
                await on_event(error_event)
            yield error_event


def get_agent_service(llm_service: LLMService | None = None) -> AgentService:
    """Get an AgentService instance."""
    return AgentService(llm_service)
