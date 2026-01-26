"""HTML Capture Service - Renders HTML slides to images using Playwright."""

import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.renderers.html_slide_renderer import HTMLSlideRenderer
from app.schemas.slidespec import SlideSpec


class HTMLCaptureService:
    """Captures HTML slides as images using Playwright (sync API for Windows compatibility)."""

    # Slide dimensions (16:9 at 2x for quality)
    SLIDE_WIDTH = 1920
    SLIDE_HEIGHT = 1080

    def __init__(self):
        self._browser = None
        self._playwright = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self.renderer = HTMLSlideRenderer()

    def _ensure_browser_sync(self):
        """Ensure browser is initialized (sync version)."""
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
        return self._browser

    def close_sync(self):
        """Close browser resources (sync version)."""
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    async def close(self):
        """Close browser resources."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self.close_sync)

    def _get_full_html(self, slide_html: str) -> str:
        """Wrap slide HTML with full document including Tailwind CSS and Chart.js."""
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        primary: {{
                            50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe',
                            300: '#93c5fd', 400: '#60a5fa', 500: '#3b82f6',
                            600: '#2563eb', 700: '#1d4ed8', 800: '#1e40af', 900: '#1e3a8a',
                        }},
                        accent: {{ DEFAULT: '#8b5cf6', light: '#a78bfa', dark: '#7c3aed' }},
                    }},
                    animation: {{
                        'fade-in': 'fadeIn 0.5s ease-out forwards',
                        'slide-up': 'slideUp 0.5s ease-out forwards',
                    }},
                }}
            }}
        }}
    </script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: transparent;
        }}
        .slide {{
            width: {self.SLIDE_WIDTH}px;
            height: {self.SLIDE_HEIGHT}px;
            margin: 0;
            border-radius: 0;
            box-shadow: none;
        }}
        .gradient-primary {{ background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); }}
        .gradient-accent {{ background: linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%); }}
        .gradient-dark {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); }}
        .chart-gradient {{ background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 50%, #bae6fd 100%); }}
    </style>
</head>
<body>
{slide_html}
<script>
// Chart.js initialization
function initializeCharts() {{
    const colors = [
        {{ bg: 'rgba(59, 130, 246, 0.7)', border: 'rgb(59, 130, 246)' }},
        {{ bg: 'rgba(139, 92, 246, 0.7)', border: 'rgb(139, 92, 246)' }},
        {{ bg: 'rgba(16, 185, 129, 0.7)', border: 'rgb(16, 185, 129)' }},
        {{ bg: 'rgba(249, 115, 22, 0.7)', border: 'rgb(249, 115, 22)' }},
        {{ bg: 'rgba(236, 72, 153, 0.7)', border: 'rgb(236, 72, 153)' }},
        {{ bg: 'rgba(99, 102, 241, 0.7)', border: 'rgb(99, 102, 241)' }},
    ];

    document.querySelectorAll('.chart-container[data-chart]').forEach(function(container) {{
        if (container.dataset.initialized === 'true') return;

        const canvas = container.querySelector('canvas');
        if (!canvas) return;

        try {{
            const chartData = JSON.parse(container.dataset.chart);
            const chartType = chartData.chart_type;
            const series = chartData.series || [];
            const title = chartData.title || '';

            let labels = [];
            let datasets = [];

            if (chartType === 'pie') {{
                if (series.length > 0) {{
                    labels = series[0].data.map(d => String(d.x));
                    datasets = [{{
                        data: series[0].data.map(d => d.y),
                        backgroundColor: series[0].data.map((_, i) => colors[i % colors.length].bg),
                        borderColor: series[0].data.map((_, i) => colors[i % colors.length].border),
                        borderWidth: 2,
                    }}];
                }}
            }} else {{
                if (series.length > 0) {{
                    labels = series[0].data.map(d => String(d.x));
                }}
                datasets = series.map((s, idx) => ({{
                    label: s.name,
                    data: s.data.map(d => d.y),
                    backgroundColor: colors[idx % colors.length].bg,
                    borderColor: colors[idx % colors.length].border,
                    borderWidth: 2,
                    fill: chartType === 'area',
                    tension: chartType === 'line' || chartType === 'area' ? 0.3 : 0,
                }}));
            }}

            let type = chartType;
            if (type === 'area') type = 'line';
            if (type === 'stacked_bar') type = 'bar';

            const config = {{
                type: type,
                data: {{ labels: labels, datasets: datasets }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    layout: {{
                        padding: {{ top: 10, right: 15, bottom: 10, left: 15 }}
                    }},
                    plugins: {{
                        legend: {{
                            display: series.length > 1 || chartType === 'pie',
                            position: chartType === 'pie' ? 'right' : 'top',
                            labels: {{
                                font: {{ size: 12 }},
                                padding: 15,
                                boxWidth: 12,
                            }},
                        }},
                        title: {{
                            display: !!title,
                            text: title,
                            font: {{ size: 16, weight: 'bold' }},
                            padding: {{ bottom: 15 }},
                        }},
                    }},
                    scales: chartType === 'pie' ? {{}} : {{
                        x: {{
                            title: {{
                                display: !!chartData.x_label,
                                text: chartData.x_label || '',
                                font: {{ size: 12 }},
                                padding: {{ top: 8 }}
                            }},
                            ticks: {{
                                font: {{ size: 11 }},
                                maxRotation: 45,
                                minRotation: 0,
                            }},
                            grid: {{ display: false }},
                            stacked: chartType === 'stacked_bar',
                        }},
                        y: {{
                            title: {{
                                display: !!chartData.y_label,
                                text: chartData.y_label || '',
                                font: {{ size: 12 }},
                                padding: {{ bottom: 8 }}
                            }},
                            ticks: {{
                                font: {{ size: 11 }},
                            }},
                            beginAtZero: true,
                            stacked: chartType === 'stacked_bar',
                        }},
                    }},
                }},
            }};

            new Chart(canvas, config);
            container.dataset.initialized = 'true';
        }} catch (e) {{
            console.error('Failed to initialize chart:', e);
        }}
    }});

    // Signal that charts are ready
    window.chartsInitialized = true;
}}

// Initialize charts when DOM is ready
if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initializeCharts);
}} else {{
    initializeCharts();
}}
</script>
</body>
</html>"""

    def _capture_slide_html_sync(self, slide_html: str) -> bytes:
        """Capture a slide HTML as PNG image bytes (sync version)."""
        browser = self._ensure_browser_sync()
        page = browser.new_page(viewport={'width': self.SLIDE_WIDTH, 'height': self.SLIDE_HEIGHT})

        try:
            # Set content with full HTML
            full_html = self._get_full_html(slide_html)
            page.set_content(full_html, wait_until='networkidle')

            # Wait for Tailwind to process
            page.wait_for_timeout(500)

            # Wait for Chart.js to initialize (if charts exist)
            has_charts = page.query_selector('.chart-container[data-chart]') is not None
            if has_charts:
                # Wait for charts to be initialized (max 3 seconds)
                try:
                    page.wait_for_function(
                        'window.chartsInitialized === true',
                        timeout=3000
                    )
                    # Additional wait for Chart.js animation to complete
                    page.wait_for_timeout(500)
                except Exception:
                    # If wait times out, continue anyway
                    page.wait_for_timeout(1000)

            # Find the slide element and screenshot it
            slide = page.query_selector('.slide')
            if slide:
                screenshot = slide.screenshot(type='png')
            else:
                # Fallback to full page
                screenshot = page.screenshot(type='png')

            return screenshot

        finally:
            page.close()

    async def capture_slide_html(self, slide_html: str) -> bytes:
        """Capture a slide HTML as PNG image bytes."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._capture_slide_html_sync,
            slide_html
        )

    def _capture_slidespec_sync(self, slidespec: SlideSpec) -> list[bytes]:
        """Capture all slides from a SlideSpec as PNG images (sync version)."""
        images = []

        for idx, slide in enumerate(slidespec.slides):
            # Render slide to HTML
            html = self.renderer.render_slide(slide, idx)
            # Capture as image
            image_bytes = self._capture_slide_html_sync(html)
            images.append(image_bytes)

        return images

    async def capture_slidespec(self, slidespec: SlideSpec) -> list[bytes]:
        """Capture all slides from a SlideSpec as PNG images."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._capture_slidespec_sync,
            slidespec
        )

    def _capture_html_slides_sync(self, html_slides: list[str]) -> list[bytes]:
        """Capture multiple HTML slides as PNG images (sync version)."""
        images = []
        for html in html_slides:
            image_bytes = self._capture_slide_html_sync(html)
            images.append(image_bytes)
        return images

    async def capture_html_slides(self, html_slides: list[str]) -> list[bytes]:
        """Capture multiple HTML slides as PNG images."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._capture_html_slides_sync,
            html_slides
        )


# Singleton instance
_capture_service: Optional[HTMLCaptureService] = None


def get_html_capture_service() -> HTMLCaptureService:
    """Get the HTML capture service singleton."""
    global _capture_service
    if _capture_service is None:
        _capture_service = HTMLCaptureService()
    return _capture_service
