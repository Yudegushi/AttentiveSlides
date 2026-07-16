from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFilter

from modules.attention.gaze_heatmap import SlideHeatmapSnapshot


MAX_ALPHA = 165
COLOR_STOPS = (
    (0.00, (37, 99, 235)),
    (0.25, (6, 182, 212)),
    (0.50, (250, 204, 21)),
    (0.75, (249, 115, 22)),
    (1.00, (220, 38, 38)),
)


def _channel_luts() -> tuple[list[int], list[int], list[int], list[int]]:
    red, green, blue, alpha = [], [], [], []
    for index in range(256):
        value = index / 255.0
        left, right = COLOR_STOPS[0], COLOR_STOPS[-1]
        for start, end in zip(COLOR_STOPS, COLOR_STOPS[1:]):
            if start[0] <= value <= end[0]:
                left, right = start, end
                break
        span = max(1e-9, right[0] - left[0])
        blend = (value - left[0]) / span
        color = tuple(
            round(a + blend * (b - a))
            for a, b in zip(left[1], right[1])
        )
        red.append(color[0])
        green.append(color[1])
        blue.append(color[2])
        alpha.append(round(MAX_ALPHA * value))
    return red, green, blue, alpha


RED_LUT, GREEN_LUT, BLUE_LUT, ALPHA_LUT = _channel_luts()


def _heatmap_overlay(slide: SlideHeatmapSnapshot, size: tuple[int, int]) -> Image.Image:
    maximum = max(slide.grid, default=0.0)
    if maximum <= 0.0:
        return Image.new("RGBA", size, color=(0, 0, 0, 0))
    pixels = bytes(round(255 * value / maximum) for value in slide.grid)
    intensity = Image.frombytes("L", (slide.grid_width, slide.grid_height), pixels)
    try:
        resized = intensity.resize(size, Image.Resampling.BICUBIC)
        radius = max(6, round(min(size) * 0.025))
        blurred = resized.filter(ImageFilter.GaussianBlur(radius=radius))
        resized.close()
        channels = (
            blurred.point(RED_LUT),
            blurred.point(GREEN_LUT),
            blurred.point(BLUE_LUT),
            blurred.point(ALPHA_LUT),
        )
        try:
            return Image.merge("RGBA", channels)
        finally:
            blurred.close()
            for channel in channels:
                channel.close()
    finally:
        intensity.close()


def render_review_slide(
    image_path: str | Path,
    slide: SlideHeatmapSnapshot,
    *,
    show_heatmap: bool = True,
) -> Image.Image:
    with Image.open(image_path) as source:
        base = source.convert("RGBA")
    if not show_heatmap or max(slide.grid, default=0.0) <= 0.0:
        result = base.convert("RGB")
        base.close()
        return result
    overlay = _heatmap_overlay(slide, base.size)
    try:
        composite = Image.alpha_composite(base, overlay)
        result = composite.convert("RGB")
        composite.close()
        return result
    finally:
        overlay.close()
        base.close()


def review_png_bytes(
    image_path: str | Path,
    slide: SlideHeatmapSnapshot,
    *,
    show_heatmap: bool = True,
) -> bytes:
    image = render_review_slide(image_path, slide, show_heatmap=show_heatmap)
    try:
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()
    finally:
        image.close()
