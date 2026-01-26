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

SLIDESPEC_SYSTEM_PROMPT = """You are a presentation content generator that creates detailed slide specifications with custom Tailwind CSS styling.
Given an outline and requirements, generate a complete SlideSpec JSON with creative styling.

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
      "tailwind_classes": "optional custom classes for slide container",
      "elements": [
        {
          "element_id": "s1_e1",
          "kind": "text|bullets|image|chart|table",
          "role": "title|subtitle|body|visual",
          "content": {...},
          "tailwind_classes": "optional custom Tailwind classes"
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

Tailwind CSS Styling Guidelines:
You can use "tailwind_classes" on slides and elements for custom styling.

Available Tailwind classes (using CDN):
- Colors: text-red-500, bg-blue-100, border-green-300, etc.
- Custom colors: primary-50 to primary-900, accent, accent-light, accent-dark
- Typography: text-sm, text-lg, text-xl, text-2xl, font-bold, font-light, italic, tracking-wide
- Spacing: p-4, px-6, py-2, m-4, mx-auto, gap-4
- Layout: flex, grid, items-center, justify-center, space-y-4
- Effects: shadow-lg, rounded-xl, opacity-80, blur-sm
- Animations: animate-pulse, animate-bounce, transition-all
- Borders: border, border-2, border-dashed, rounded-full
- Backgrounds: bg-gradient-to-r, from-purple-500, to-pink-500

Example tailwind_classes usage:
- Slide: "bg-gradient-to-br from-indigo-900 to-purple-900"
- Title: "text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500"
- Text: "text-lg text-gray-300 leading-relaxed"
- Bullets: "text-emerald-400 font-medium"

Rules:
- slide_id format: s1, s2, s3...
- element_id format: s1_e1, s1_e2...
- Keep bullet points concise (max 8 per slide)
- Use appropriate layouts for content type
- Add speaker notes with key talking points
- Use tailwind_classes creatively to enhance visual appeal
- Match styling to the presentation's tone (professional, creative, playful, etc.)
- Output ONLY valid JSON"""

SINGLE_SLIDE_SYSTEM_PROMPT = """You are a presentation content generator. Generate a SINGLE slide specification with Tailwind CSS styling.

Output ONLY valid JSON for ONE slide (no schema_version, no deck, just the slide object):
{
  "slide_id": "s1",
  "type": "title|section|content|closing",
  "layout": {"layout_id": "layout_name"},
  "tailwind_classes": "optional custom classes",
  "elements": [
    {
      "element_id": "s1_e1",
      "kind": "text|bullets|image|chart|table",
      "role": "title|subtitle|body|visual",
      "content": {...},
      "tailwind_classes": "optional custom Tailwind classes"
    }
  ],
  "speaker_notes": "optional"
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

Tailwind CSS examples:
- Slide: "bg-gradient-to-br from-indigo-900 to-purple-900"
- Title: "text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500"
- Text: "text-lg text-gray-300"

Rules:
- Output ONLY valid JSON for ONE slide
- Use appropriate layout for content type
- Keep bullet points concise (max 6 items)
- Use tailwind_classes creatively"""


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

    async def generate_single_slide(
        self,
        slide_index: int,
        slide_info: dict,
        presentation_context: dict,
        language: str = "ko",
    ) -> dict:
        """Generate a single slide based on outline info."""
        slide_type = slide_info.get("type", "content")
        title = slide_info.get("title", "")
        key_points = slide_info.get("key_points", [])

        user_prompt = f"""Generate slide #{slide_index + 1} for presentation: "{presentation_context.get('title', '')}"

Slide info:
- Type: {slide_type}
- Title: {title}
- Key points to cover: {json.dumps(key_points, ensure_ascii=False)}

Context:
- Language: {language}
- Audience: {presentation_context.get('audience', 'General')}
- Tone: {presentation_context.get('tone', 'Professional')}
- Total slides: {presentation_context.get('total_slides', 10)}

Generate the slide JSON with slide_id "s{slide_index + 1}"."""

        result = await self.llm.generate_json(user_prompt, SINGLE_SLIDE_SYSTEM_PROMPT)

        # Ensure slide_id is correct
        result["slide_id"] = f"s{slide_index + 1}"

        return result

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
        Each slide is generated and rendered individually for real-time feedback.
        """
        run_id = str(uuid.uuid4())
        generated_slides = []

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
                    "progress": 5.0,
                    "message": "Generating outline...",
                },
            )
            if on_event:
                await on_event(progress_event)
            yield progress_event

            print(f"[LLM] Generating outline...")
            outline = await self.generate_outline(
                prompt, language, audience, tone, slide_count
            )
            print(f"[LLM] Outline generated: {outline.get('title', 'Untitled')}")

            # Build slide list from outline
            slide_infos = self._build_slide_list_from_outline(outline)
            total_slides = len(slide_infos)

            print(f"[Planning] Total slides to generate: {total_slides}")

            # Presentation context for slide generation
            presentation_context = {
                "title": outline.get("title", "Presentation"),
                "audience": audience or "General",
                "tone": tone or "Professional",
                "total_slides": total_slides,
                "prompt": prompt,
            }

            progress_event = SSEEvent(
                event=SSEEventType.RUN_PROGRESS,
                run_id=run_id,
                data={
                    "status": RunStatus.GENERATING.value,
                    "progress": 10.0,
                    "message": f"Generating {total_slides} slides...",
                    "total_slides": total_slides,
                },
            )
            if on_event:
                await on_event(progress_event)
            yield progress_event

            # Generate and render each slide one by one
            for idx, slide_info in enumerate(slide_infos):
                print(f"[LLM] Generating slide {idx + 1}/{total_slides}: {slide_info.get('title', 'Untitled')}")

                # Slide start
                slide_start_event = SSEEvent(
                    event=SSEEventType.SLIDE_START,
                    run_id=run_id,
                    data={
                        "slide_id": f"s{idx + 1}",
                        "slide_index": idx,
                        "total_slides": total_slides,
                        "slide_title": slide_info.get("title", ""),
                    },
                )
                if on_event:
                    await on_event(slide_start_event)
                yield slide_start_event

                # Generate single slide
                slide_dict = await self.generate_single_slide(
                    idx, slide_info, presentation_context, language
                )
                generated_slides.append(slide_dict)

                # Validate and render
                from app.schemas.slidespec import Slide
                slide = Slide.model_validate(slide_dict)

                # Render slide HTML
                html = self.renderer.render_slide(slide, idx)
                print(f"[HTML Generated] Slide {idx + 1}: {len(html)} bytes")

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
                progress = 10.0 + (idx + 1) / total_slides * 85.0
                progress_event = SSEEvent(
                    event=SSEEventType.RUN_PROGRESS,
                    run_id=run_id,
                    data={
                        "status": RunStatus.GENERATING.value,
                        "progress": progress,
                        "current_slide": idx + 1,
                        "total_slides": total_slides,
                        "message": f"Generated slide {idx + 1} of {total_slides}",
                    },
                )
                if on_event:
                    await on_event(progress_event)
                yield progress_event

            # Build complete SlideSpec
            slidespec_dict = {
                "schema_version": "slidespec_v1",
                "deck": {
                    "title": outline.get("title", "Presentation"),
                    "subtitle": outline.get("subtitle"),
                    "language": language,
                    "audience": audience,
                    "tone": tone,
                },
                "slides": generated_slides,
            }
            slidespec = SlideSpec.model_validate(slidespec_dict)

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
            import traceback
            traceback.print_exc()
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

    def _build_slide_list_from_outline(self, outline: dict) -> list[dict]:
        """Build a flat list of slide info from the outline structure."""
        slides = []

        title = outline.get("title", "Presentation")

        # Title slide
        slides.append({
            "type": "title",
            "title": title,
            "key_points": [outline.get("subtitle", "")],
        })

        # Section slides
        sections = outline.get("sections", [])
        for section in sections:
            section_title = section.get("title", "Section")
            section_slides = section.get("slides", 1)
            key_points = section.get("key_points", [])

            # Section header slide
            slides.append({
                "type": "section",
                "title": section_title,
                "key_points": key_points[:2] if key_points else [],
            })

            # Content slides for this section
            points_per_slide = max(1, len(key_points) // max(1, section_slides - 1)) if section_slides > 1 else len(key_points)
            for i in range(max(0, section_slides - 1)):
                start = i * points_per_slide
                end = start + points_per_slide
                slide_points = key_points[start:end] if key_points else []

                slides.append({
                    "type": "content",
                    "title": f"{section_title} - Details" if section_slides > 2 else section_title,
                    "key_points": slide_points or [f"Details for {section_title}"],
                })

        # Closing slide
        slides.append({
            "type": "closing",
            "title": "Thank You",
            "key_points": ["Questions?", "Contact information"],
        })

        return slides


def get_agent_service(llm_service: LLMService | None = None) -> AgentService:
    """Get an AgentService instance."""
    return AgentService(llm_service)
