"""SlideSpec Pydantic schemas based on specs/schemas/ir/slidespec_v1.schema.json"""

from typing import Literal, Any
from pydantic import BaseModel, Field


class LayoutRef(BaseModel):
    """Layout reference for a slide."""

    layout_id: str = Field(..., min_length=1, max_length=120)
    variant: str | None = Field(None, max_length=120)
    hints: dict[str, Any] | None = None


class Citation(BaseModel):
    """Citation/evidence reference."""

    id: str = Field(..., min_length=1, max_length=80)
    kind: Literal["evidence", "url", "note"] = "evidence"
    evidence_id: str | None = Field(None, max_length=80)  # Made optional
    title: str | None = Field(None, max_length=300)
    source: str | None = Field(None, max_length=300)
    locator: dict[str, Any] | None = None
    quote: str | None = Field(None, max_length=2000)
    url: str | None = None


class TextContent(BaseModel):
    """Text element content."""

    text: str = Field(..., min_length=1, max_length=20000)
    format: Literal["plain", "markdown"] = "plain"


class BulletsItem(BaseModel):
    """Nested bullet item."""

    text: str = Field(..., min_length=1, max_length=2000)
    children: list["BulletsItem"] | None = None


class BulletsContent(BaseModel):
    """Bullets element content."""

    items: list[str | BulletsItem] = Field(..., min_length=1, max_length=200)


class ImageContent(BaseModel):
    """Image element content."""

    asset_id: str | None = Field(None, min_length=1)
    url: str | None = None
    alt_text: str | None = Field(None, max_length=500)
    caption: str | None = Field(None, max_length=500)
    crop_hint: Literal["contain", "cover", "center_crop"] | None = None


class ChartPoint(BaseModel):
    """Single data point in a chart series."""

    x: str | float | int
    y: float | int


class ChartSeries(BaseModel):
    """Chart data series."""

    name: str = Field(..., min_length=1, max_length=200)
    data: list[ChartPoint] = Field(..., min_length=1, max_length=5000)


class ChartContent(BaseModel):
    """Chart element content."""

    chart_type: Literal["bar", "line", "pie", "area", "stacked_bar"]
    title: str | None = Field(None, max_length=200)
    x_label: str | None = Field(None, max_length=100)
    y_label: str | None = Field(None, max_length=100)
    series: list[ChartSeries] = Field(..., min_length=1, max_length=30)
    options: dict[str, Any] | None = None


class TableContent(BaseModel):
    """Table element content."""

    title: str | None = Field(None, max_length=200)
    columns: list[str] = Field(..., min_length=1, max_length=50)
    rows: list[list[str | float | int | None]] = Field(..., min_length=1, max_length=5000)
    options: dict[str, Any] | None = None


class StyleOverrides(BaseModel):
    """Element style overrides."""

    font_family: str | None = Field(None, max_length=200)
    font_pt: float | None = Field(None, ge=1, le=200)
    bold: bool | None = None
    italic: bool | None = None
    color_hex: str | None = None
    align: Literal["left", "center", "right", "justify"] | None = None


# 배경 프리셋 타입
BackgroundPreset = Literal[
    "bg-white",           # 기본 흰 배경
    "bg-slate-50",        # 연한 회색 (데이터/표에 적합)
    "bg-slate-100",       # 회색 배경
    "gradient-primary",   # 파랑 그라데이션 (타이틀, 강조)
    "gradient-dark",      # 어두운 배경 (인용, 임팩트)
    "gradient-warm",      # 오렌지/핑크 그라데이션 (마케팅, 창의적)
    "gradient-green",     # 그린 계열 (성장, 환경)
    "gradient-purple",    # 보라 계열 (혁신, 기술)
    "gradient-ocean",     # 청록 계열 (신뢰, 안정)
]

# 색상 테마 타입
ColorScheme = Literal[
    "default",       # 기본 (파란 계열 액센트)
    "professional",  # 프로페셔널 (네이비, 그레이)
    "creative",      # 크리에이티브 (다채로운 색상)
    "bold",          # 볼드 (강렬한 대비)
    "minimal",       # 미니멀 (흑백 위주)
    "warm",          # 따뜻한 (오렌지, 레드 계열)
    "cool",          # 차가운 (블루, 그린 계열)
    "nature",        # 자연 (그린, 브라운 계열)
]


class SlideStyle(BaseModel):
    """슬라이드 스타일 설정."""

    background: BackgroundPreset = Field(
        default="bg-white",
        description="슬라이드 배경 프리셋"
    )
    color_scheme: ColorScheme = Field(
        default="default",
        description="색상 테마"
    )
    accent_color: str | None = Field(
        None,
        max_length=20,
        description="커스텀 액센트 컬러 (hex 또는 Tailwind 색상명)"
    )
    text_color: Literal["light", "dark", "auto"] = Field(
        default="auto",
        description="텍스트 색상 (auto면 배경에 따라 자동 결정)"
    )


class Element(BaseModel):
    """Slide element (text, bullets, image, chart, table, etc.)."""

    element_id: str = Field(..., min_length=1, max_length=120)
    kind: Literal["text", "bullets", "image", "chart", "table", "shape", "divider"]
    role: str | None = Field(None, max_length=80)
    content: dict[str, Any]  # Type depends on kind
    citations: list[Citation] | None = None
    style_overrides: StyleOverrides | None = None
    tailwind_classes: str | None = Field(None, max_length=1000, description="Custom Tailwind CSS classes for this element")
    extensions: dict[str, Any] | None = None


class Slide(BaseModel):
    """Single slide in a deck."""

    slide_id: str = Field(..., min_length=1, max_length=120)
    type: Literal["title", "section", "content", "closing", "appendix"] = "content"
    layout: LayoutRef | None = None  # Made optional - LLM may not always provide
    title: str | None = Field(None, max_length=500)
    elements: list[Element] = Field(default_factory=list, max_length=200)
    citations: list[Citation] | None = None
    speaker_notes: str | None = Field(None, max_length=10000)
    style: SlideStyle | None = Field(
        default=None,
        description="슬라이드 스타일 설정 (배경, 색상 테마 등)"
    )
    tailwind_classes: str | None = Field(None, max_length=1000, description="Custom Tailwind CSS classes for the slide container")
    extensions: dict[str, Any] | None = None


class DeckMeta(BaseModel):
    """Deck metadata."""

    title: str = Field(..., min_length=1, max_length=300)
    subtitle: str | None = Field(None, max_length=500)
    language: str = Field(..., min_length=2, max_length=20)
    audience: str | None = Field(None, max_length=200)
    tone: str | None = Field(None, max_length=200)
    metadata: dict[str, Any] | None = None


class TemplateRef(BaseModel):
    """Template and brand kit reference."""

    template_id: str | None = Field(None, min_length=1)
    brand_kit_id: str | None = Field(None, min_length=1)
    slide_size: str | None = Field(None, max_length=80)


class AssetRef(BaseModel):
    """Asset reference."""

    asset_id: str = Field(..., min_length=1, max_length=120)
    kind: Literal["image", "file", "chart_data", "other"] | None = None
    label: str | None = Field(None, max_length=200)
    hint: str | None = Field(None, max_length=1000)


class DeckStyle(BaseModel):
    """전체 덱에 적용되는 기본 스타일."""

    default_background: BackgroundPreset = Field(
        default="bg-white",
        description="기본 슬라이드 배경"
    )
    color_scheme: ColorScheme = Field(
        default="default",
        description="전체 덱 색상 테마"
    )
    accent_color: str | None = Field(
        None,
        max_length=20,
        description="커스텀 액센트 컬러"
    )


class SlideSpec(BaseModel):
    """Complete slide deck specification (SlideSpec v1)."""

    schema_version: Literal["slidespec_v1"] = "slidespec_v1"
    deck: DeckMeta
    template: TemplateRef | None = None
    style: DeckStyle | None = Field(
        default=None,
        description="전체 덱 기본 스타일 (개별 슬라이드에서 오버라이드 가능)"
    )
    assets: list[AssetRef] | None = None
    slides: list[Slide] = Field(..., min_length=1, max_length=500)
    extensions: dict[str, Any] | None = None
