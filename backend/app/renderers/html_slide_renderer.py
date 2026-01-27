"""HTML Slide Renderer - Converts SlideSpec to HTML for preview."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.schemas.slidespec import SlideSpec, Slide, Element, SlideStyle, DeckStyle


class HTMLSlideRenderer:
    """Renders SlideSpec to HTML slides for real-time preview."""

    # Layout ID to template file mapping
    LAYOUT_TEMPLATES = {
        "title_center": "title_center.html",
        "section_header": "section_header.html",
        "one_column": "one_column.html",
        "two_column": "two_column.html",
        "chart_focus": "chart_focus.html",
        "table_focus": "table_focus.html",
        "quote_center": "quote_center.html",
        "closing": "closing.html",
    }

    # Slide type to default layout mapping
    TYPE_DEFAULT_LAYOUTS = {
        "title": "title_center",
        "section": "section_header",
        "content": "one_column",
        "closing": "closing",
        "appendix": "one_column",
    }

    # 어두운 배경 목록 (텍스트 색상 자동 결정용)
    DARK_BACKGROUNDS = {
        "gradient-primary",
        "gradient-dark",
        "gradient-purple",
        "gradient-ocean",
    }

    def __init__(self, templates_path: Path | str | None = None):
        """Initialize the renderer with templates path."""
        if templates_path is None:
            templates_path = Path(__file__).parent.parent / "templates" / "slides"
        else:
            templates_path = Path(templates_path)

        self.templates_path = templates_path
        self.env = Environment(
            loader=FileSystemLoader(str(templates_path)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def get_layout_template(self, slide: Slide) -> str:
        """Get the template file name for a slide based on layout or type."""
        layout_id = slide.layout.layout_id if slide.layout else None

        # Try to get template by layout_id
        if layout_id and layout_id in self.LAYOUT_TEMPLATES:
            return self.LAYOUT_TEMPLATES[layout_id]

        # Fall back to type-based default
        default_layout = self.TYPE_DEFAULT_LAYOUTS.get(slide.type, "one_column")
        return self.LAYOUT_TEMPLATES.get(default_layout, "one_column.html")

    def get_style_context(self, slide: Slide, deck_style: DeckStyle | None = None) -> dict[str, Any]:
        """슬라이드 스타일 컨텍스트 생성."""
        style = slide.style

        # 슬라이드 스타일 또는 덱 기본 스타일 사용
        background = "bg-white"
        color_scheme = "default"
        accent_color = None
        text_color = "auto"

        if style:
            background = style.background
            color_scheme = style.color_scheme
            accent_color = style.accent_color
            text_color = style.text_color
        elif deck_style:
            background = deck_style.default_background
            color_scheme = deck_style.color_scheme
            accent_color = deck_style.accent_color

        # 텍스트 색상 자동 결정
        if text_color == "auto":
            text_color = "light" if background in self.DARK_BACKGROUNDS else "dark"

        # CSS 클래스 생성
        style_classes = []

        # 배경 클래스
        if background.startswith("gradient-"):
            style_classes.append(background)
        else:
            style_classes.append(background)  # bg-white, bg-slate-50 등

        # 색상 테마 클래스
        style_classes.append(f"scheme-{color_scheme}")

        # 텍스트 테마 클래스
        style_classes.append(f"text-theme-{text_color}")

        return {
            "style_classes": " ".join(style_classes),
            "background": background,
            "color_scheme": color_scheme,
            "accent_color": accent_color,
            "text_color": text_color,
            "is_dark_bg": text_color == "light",
        }

    def render_slide(self, slide: Slide, slide_index: int = 0, deck_style: DeckStyle | None = None) -> str:
        """Render a single slide to HTML."""
        template_file = self.get_layout_template(slide)
        template = self.env.get_template(template_file)

        # Prepare elements data
        elements = []
        for elem in slide.elements:
            elements.append({
                "element_id": elem.element_id,
                "kind": elem.kind,
                "role": elem.role,
                "content": elem.content,
                "citations": [c.model_dump() for c in elem.citations] if elem.citations else [],
                "style_overrides": elem.style_overrides.model_dump() if elem.style_overrides else None,
                "tailwind_classes": elem.tailwind_classes or "",
            })

        # Prepare citations data
        citations = []
        if slide.citations:
            for c in slide.citations:
                citations.append(c.model_dump())

        # 스타일 컨텍스트 생성
        style_context = self.get_style_context(slide, deck_style)

        context = {
            "slide_id": slide.slide_id,
            "slide_type": slide.type,
            "slide_index": slide_index,
            "layout_id": slide.layout.layout_id if slide.layout else "one_column",
            "title": slide.title,
            "elements": elements,
            "citations": citations,
            "speaker_notes": slide.speaker_notes,
            "slide_tailwind_classes": slide.tailwind_classes or "",
            # 스타일 관련 컨텍스트
            **style_context,
        }

        return template.render(**context)

    def render_deck(self, slidespec: SlideSpec) -> str:
        """Render the entire deck to HTML."""
        base_template = self.env.get_template("base.html")
        deck_style = slidespec.style

        slides_html = []
        for idx, slide in enumerate(slidespec.slides):
            slide_html = self.render_slide(slide, idx, deck_style)
            slides_html.append(slide_html)

        content = "\n".join(slides_html)

        return base_template.render(
            deck_title=slidespec.deck.title,
            language=slidespec.deck.language,
            content=content,
        )

    def render_slide_dict(
        self,
        slide_dict: dict[str, Any],
        slide_index: int = 0,
        deck_style: DeckStyle | None = None
    ) -> str:
        """Render a slide from a dictionary (useful for streaming partial results)."""
        # Convert dict to Slide object for consistent rendering
        slide = Slide.model_validate(slide_dict)
        return self.render_slide(slide, slide_index, deck_style)

    def get_slide_wrapper(self, slide_id: str, slide_index: int, html_content: str) -> str:
        """Wrap slide content in a container div for streaming updates."""
        return f'''<div id="slide-{slide_id}" class="slide-wrapper" data-index="{slide_index}">
{html_content}
</div>'''

    def get_base_styles(self) -> str:
        """Get the base CSS styles for slides."""
        base_template_path = self.templates_path / "base.html"
        if base_template_path.exists():
            content = base_template_path.read_text(encoding="utf-8")
            # Extract style content from base template
            import re
            style_match = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
            if style_match:
                return style_match.group(1)
        return ""
