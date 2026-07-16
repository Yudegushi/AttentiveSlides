from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageChops

from modules.attention.gaze_heatmap import SlideHeatmapSnapshot
from modules.attention.heatmap_renderer import (
    _heatmap_overlay,
    render_review_slide,
    review_png_bytes,
)


def snapshot(grid, *, width=4, height=2):
    return SlideHeatmapSnapshot(
        deck_id="deck-a",
        slide_id=1,
        grid_width=width,
        grid_height=height,
        grid=tuple(grid),
        observed_seconds=1.0,
        valid_gaze_seconds=sum(grid),
        aoi_dwell=(),
    )


class HeatmapRendererTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.image_path = Path(self.temporary.name) / "slide.png"
        Image.new("RGB", (320, 180), color=(245, 245, 240)).save(self.image_path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_hot_grid_changes_pixels_without_changing_size(self):
        rendered = render_review_slide(
            self.image_path,
            snapshot([0, 0, 0, 0, 0, 0, 1, 0]),
        )
        original = Image.open(self.image_path).convert("RGB")
        try:
            self.assertEqual(rendered.size, original.size)
            self.assertIsNotNone(ImageChops.difference(rendered, original).getbbox())
        finally:
            rendered.close()
            original.close()

    def test_production_grid_reaches_red_after_blur(self):
        width, height = 64, 36
        grid = [0.0] * (width * height)
        grid[27 * width + 48] = 1.0
        overlay = _heatmap_overlay(
            snapshot(grid, width=width, height=height),
            (320, 180),
        )
        try:
            hottest_x, hottest_y, hottest_rgba = max(
                (
                    (x, y, overlay.getpixel((x, y)))
                    for y in range(overlay.height)
                    for x in range(overlay.width)
                ),
                key=lambda item: item[2][3],
            )

            self.assertEqual(hottest_rgba, (220, 38, 38, 165))
            self.assertGreater(hottest_x, overlay.width * 0.65)
            self.assertGreater(hottest_y, overlay.height * 0.65)
        finally:
            overlay.close()

    def test_hidden_or_empty_heatmap_returns_original_pixels(self):
        original = Image.open(self.image_path).convert("RGB")
        hidden = render_review_slide(
            self.image_path,
            snapshot([1] * 8),
            show_heatmap=False,
        )
        empty = render_review_slide(self.image_path, snapshot([0] * 8))
        try:
            self.assertIsNone(ImageChops.difference(hidden, original).getbbox())
            self.assertIsNone(ImageChops.difference(empty, original).getbbox())
        finally:
            original.close()
            hidden.close()
            empty.close()

    def test_png_export_is_decodable_at_source_dimensions(self):
        payload = review_png_bytes(
            self.image_path,
            snapshot([0, 0, 0, 0, 0, 1, 0, 0]),
        )

        exported = Image.open(__import__("io").BytesIO(payload))
        try:
            self.assertEqual(exported.format, "PNG")
            self.assertEqual(exported.size, (320, 180))
        finally:
            exported.close()


if __name__ == "__main__":
    unittest.main()
