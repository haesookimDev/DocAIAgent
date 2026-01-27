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

SLIDESPEC_SYSTEM_PROMPT = """You are a presentation content generator that creates detailed slide specifications with custom styling.
Given an outline and requirements, generate a complete SlideSpec JSON with creative styling appropriate for each slide's purpose.

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
  "style": {
    "default_background": "bg-white",
    "color_scheme": "default",
    "accent_color": "#3b82f6"
  },
  "slides": [
    {
      "slide_id": "s1",
      "type": "title|section|content|closing",
      "layout": {"layout_id": "layout_name"},
      "style": {
        "background": "gradient-primary",
        "color_scheme": "default",
        "text_color": "auto"
      },
      "tailwind_classes": "optional custom classes",
      "elements": [
        {
          "element_id": "s1_e1",
          "kind": "text|bullets|image|chart|table",
          "role": "title|subtitle|body|visual|number|label|description",
          "content": {...},
          "tailwind_classes": "optional custom Tailwind classes"
        }
      ],
      "speaker_notes": "optional"
    }
  ]
}

=== AVAILABLE LAYOUTS (15 types) ===

Basic layouts:
- title_center: Title slides with centered text (use gradient backgrounds)
- section_header: Section divider slides (use gradient-accent or gradient-dark)
- one_column: Single column content (default for most content)
- two_column: Two column layout (for comparisons, lists)
- chart_focus: Chart with key insights bullet points
- table_focus: Table-focused layout with header
- quote_center: Quote/highlight with large text (use gradient backgrounds)
- closing: Thank you/closing slides (use gradient-primary)

Extended layouts:
- image_left: Left image (40%) + right text content (60%)
- image_right: Left text content (60%) + right image (40%)
- three_column: Three equal columns (good for comparing 3 items)
- stats_grid: 2x2 grid for statistics/numbers (use "number\\nlabel" format)
- timeline: Horizontal timeline with numbered steps (use bullets with steps)
- comparison: VS comparison with two sides (Option A vs Option B)
- big_number: Large centered number with label and description (for key metrics)

=== STYLE OPTIONS ===

Background presets (slide.style.background):
- Light backgrounds: "bg-white", "bg-slate-50", "bg-slate-100"
- Gradient backgrounds (dark, use text_color: "light"):
  - "gradient-primary": Blue gradient (professional)
  - "gradient-dark": Dark slate gradient (serious)
  - "gradient-accent": Purple gradient (creative)
  - "gradient-warm": Orange to pink gradient (energetic)
  - "gradient-green": Green gradient (growth, success)
  - "gradient-purple": Purple gradient (innovation)
  - "gradient-ocean": Cyan/teal gradient (calm, tech)

Color schemes (slide.style.color_scheme):
- "default": Standard blue accents
- "professional": Navy/conservative
- "creative": Vibrant purple/pink
- "bold": High contrast
- "minimal": Subtle grays
- "warm": Orange/amber tones
- "cool": Blue/cyan tones
- "nature": Green tones

Text color (slide.style.text_color):
- "auto": Automatically choose based on background (recommended)
- "light": White text for dark backgrounds
- "dark": Dark text for light backgrounds

=== ELEMENT CONTENT FORMATS ===

- text: {"text": "content"}
- bullets: {"items": ["item1", "item2"]}
- table: {"columns": ["A", "B"], "rows": [["a1", "b1"]]}
- chart: {"chart_type": "bar|line|pie", "title": "...", "series": [{"name": "...", "data": [{"x": "...", "y": 10}]}]}
- image: {"alt_text": "description", "caption": "optional"}

Special formats for specific layouts:
- big_number: Use text with "number\\nlabel\\ndescription" format, or separate elements with roles "number", "label", "description"
- stats_grid: Use bullets with "value\\nlabel" or "value:label" format for each stat
- timeline: Use bullets where each item is a step ("Step title\\nDescription" or "Step title:Description")
- comparison: Provide 2 text or bullets elements for Option A and Option B

=== STYLING RULES ===

1. Match background to slide purpose:
   - Title slides: gradient-primary or gradient-accent
   - Section headers: gradient-dark or gradient-accent
   - Data/stats slides: bg-white or bg-slate-50
   - Key insights: gradient-warm or gradient-green
   - Closing: gradient-primary

2. Vary backgrounds throughout presentation:
   - Don't use same background for all slides
   - Alternate between light and dark backgrounds
   - Use gradients for emphasis slides

3. Choose layouts wisely:
   - timeline: for processes, steps, roadmaps
   - stats_grid: for 3-4 key numbers/metrics
   - big_number: for single important metric
   - comparison: for pros/cons, before/after, option A vs B
   - three_column: for 3 categories or options

4. Additional Tailwind classes:
   You can still use tailwind_classes for extra customization on slides and elements.

Rules:
- slide_id format: s1, s2, s3...
- element_id format: s1_e1, s1_e2...
- Keep bullet points concise (max 8 per slide)
- Use appropriate layouts for content type
- Add speaker notes with key talking points
- Vary styles across slides for visual interest
- Output ONLY valid JSON"""

SINGLE_SLIDE_SYSTEM_PROMPT = """You are a presentation content generator. Generate a SINGLE slide specification with appropriate styling.

Output ONLY valid JSON for ONE slide:
{
  "slide_id": "s1",
  "type": "title|section|content|closing",
  "layout": {"layout_id": "layout_name"},
  "style": {
    "background": "bg-white|gradient-primary|gradient-dark|etc",
    "color_scheme": "default",
    "text_color": "auto"
  },
  "tailwind_classes": "optional custom classes",
  "elements": [
    {
      "element_id": "s1_e1",
      "kind": "text|bullets|image|chart|table",
      "role": "title|subtitle|body|visual|number|label|description",
      "content": {...},
      "tailwind_classes": "optional"
    }
  ],
  "speaker_notes": "optional"
}

=== LAYOUTS (15 types) ===
Basic: title_center, section_header, one_column, two_column, chart_focus, table_focus, quote_center, closing
Extended: image_left, image_right, three_column, stats_grid, timeline, comparison, big_number

=== BACKGROUNDS ===
Light: "bg-white", "bg-slate-50", "bg-slate-100"
Gradients (dark): "gradient-primary" (blue), "gradient-dark" (slate), "gradient-accent" (purple), "gradient-warm" (orange-pink), "gradient-green", "gradient-purple", "gradient-ocean" (cyan)

=== LAYOUT USAGE ===
- timeline: for steps/process (bullets with "Step\\nDescription" format)
- stats_grid: for 2-4 key numbers (bullets with "value\\nlabel" format)
- big_number: for single key metric (text with "number\\nlabel\\ndescription")
- comparison: for A vs B (2 elements for each side)
- three_column: for 3 categories (3 text/bullets elements)

=== ELEMENT CONTENT ===
- text: {"text": "content"}
- bullets: {"items": ["item1", "item2"]}
- table: {"columns": ["A", "B"], "rows": [["a1", "b1"]]}
- chart: {"chart_type": "bar|line|pie", "title": "...", "series": [...]}

Rules:
- Match background to slide purpose (gradients for emphasis, white for data)
- Title/section slides: use gradient backgrounds
- Content slides: vary between light and gradient
- Output ONLY valid JSON for ONE slide"""


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
        suggested_layout = slide_info.get("suggested_layout", "one_column")
        suggested_style = slide_info.get("suggested_style", {})

        # Build style suggestion text
        style_suggestion = ""
        if suggested_style:
            bg = suggested_style.get("background", "bg-white")
            text_color = suggested_style.get("text_color", "auto")
            style_suggestion = f"""
Suggested style:
- Background: {bg}
- Text color: {text_color}
(Feel free to adjust based on content, but maintain visual variety)"""

        user_prompt = f"""Generate slide #{slide_index + 1} for presentation: "{presentation_context.get('title', '')}"

Slide info:
- Type: {slide_type}
- Title: {title}
- Key points to cover: {json.dumps(key_points, ensure_ascii=False)}
- Suggested layout: {suggested_layout}
{style_suggestion}

Context:
- Language: {language}
- Audience: {presentation_context.get('audience', 'General')}
- Tone: {presentation_context.get('tone', 'Professional')}
- Total slides: {presentation_context.get('total_slides', 10)}
- Current position: Slide {slide_index + 1} of {presentation_context.get('total_slides', 10)}

Generate the slide JSON with slide_id "s{slide_index + 1}".
Choose an appropriate layout and style for this slide's content and position in the presentation.
Use gradient backgrounds for title/section/closing slides, and vary styles for content slides."""

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

        # Title slide - use gradient background
        slides.append({
            "type": "title",
            "title": title,
            "key_points": [outline.get("subtitle", "")],
            "suggested_layout": "title_center",
            "suggested_style": {"background": "gradient-primary", "text_color": "light"},
        })

        # Section slides
        sections = outline.get("sections", [])
        content_slide_count = 0

        for section_idx, section in enumerate(sections):
            section_title = section.get("title", "Section")
            section_slides = section.get("slides", 1)
            key_points = section.get("key_points", [])

            # Alternate section header backgrounds
            section_backgrounds = ["gradient-accent", "gradient-dark", "gradient-ocean", "gradient-purple"]
            section_bg = section_backgrounds[section_idx % len(section_backgrounds)]

            # Section header slide
            slides.append({
                "type": "section",
                "title": section_title,
                "key_points": key_points[:2] if key_points else [],
                "suggested_layout": "section_header",
                "suggested_style": {"background": section_bg, "text_color": "light"},
            })

            # Content slides for this section
            points_per_slide = max(1, len(key_points) // max(1, section_slides - 1)) if section_slides > 1 else len(key_points)
            for i in range(max(0, section_slides - 1)):
                content_slide_count += 1
                start = i * points_per_slide
                end = start + points_per_slide
                slide_points = key_points[start:end] if key_points else []

                # Suggest varied layouts based on content and position
                suggested_layout = "one_column"
                suggested_style = {"background": "bg-white", "text_color": "dark"}

                # Every 3rd content slide, suggest a more visual layout
                if content_slide_count % 4 == 0:
                    suggested_layout = "stats_grid"
                    suggested_style = {"background": "bg-slate-50", "text_color": "dark"}
                elif content_slide_count % 4 == 2:
                    suggested_layout = "two_column"
                elif len(slide_points) >= 4:
                    # Multiple points might work well as timeline
                    suggested_layout = "timeline"

                slides.append({
                    "type": "content",
                    "title": f"{section_title} - Details" if section_slides > 2 else section_title,
                    "key_points": slide_points or [f"Details for {section_title}"],
                    "suggested_layout": suggested_layout,
                    "suggested_style": suggested_style,
                })

        # Closing slide - use gradient background
        slides.append({
            "type": "closing",
            "title": "Thank You",
            "key_points": ["Questions?", "Contact information"],
            "suggested_layout": "closing",
            "suggested_style": {"background": "gradient-primary", "text_color": "light"},
        })

        return slides


def get_agent_service(llm_service: LLMService | None = None) -> AgentService:
    """Get an AgentService instance."""
    return AgentService(llm_service)
