import unittest

from modules.common.schemas import AOI, VisualContextItem
from modules.system.main_ui_state import MainUISlide


class FakeBrowser:
    def __init__(self, deck_id, slide):
        self.deck_id = deck_id
        self._slide = slide

    def get_slide(self, slide_id):
        if slide_id != self._slide.slide_id:
            raise KeyError(slide_id)
        return self._slide


def make_browser(deck_id="deck-a", slide_id=2):
    return FakeBrowser(
        deck_id,
        MainUISlide(
            slide_id=slide_id,
            slide_text="active slide",
            neighbor_slide_text="neighbor slides",
            aois=(
                AOI(
                    aoi_id="title",
                    bbox=[0.1, 0.1, 0.9, 0.2],
                    type="title",
                    text="Title",
                    name="Title",
                ),
            ),
            image_path="/tmp/slide.png",
            visual_context=(VisualContextItem(
                visual_id="visual_1",
                type="formula",
                bbox=[0.2, 0.3, 0.7, 0.45],
                description="A conditional-probability formula.",
                transcription="p(y | x)",
                confidence=0.91,
                linked_aoi_id="title",
            ),),
        ),
    )


class ActiveDeckSlideProviderTest(unittest.TestCase):
    def make_provider(self):
        from modules.system.active_deck_slide_provider import (
            ActiveDeckSlideProvider,
        )

        return ActiveDeckSlideProvider()

    def test_copies_active_uploaded_slide_exactly(self):
        provider = self.make_provider()
        browser = make_browser()
        provider.set_browser(browser)

        frame = provider.get_slide_frame(2)

        self.assertEqual(frame.deck_id, browser.deck_id)
        self.assertEqual(frame.slide_id, 2)
        self.assertEqual([aoi.aoi_id for aoi in frame.aois], ["title"])
        self.assertEqual(frame.slide_text, "active slide")
        self.assertEqual(frame.neighbor_slide_text, "neighbor slides")
        self.assertEqual(frame.slide_image_path, "/tmp/slide.png")

    def test_main_ui_and_live_slide_frames_preserve_visual_context(self):
        provider = self.make_provider()
        browser = make_browser()
        provider.set_browser(browser)

        frame = provider.get_slide_frame(2)

        self.assertEqual(
            frame.visual_context,
            browser.get_slide(2).visual_context,
        )

    def test_requires_an_active_uploaded_deck(self):
        provider = self.make_provider()

        with self.assertRaisesRegex(RuntimeError, "No uploaded deck is active"):
            provider.get_slide_frame(2)

    def test_replacing_browser_changes_deck_atomically(self):
        provider = self.make_provider()
        provider.set_browser(make_browser("deck-a", 2))
        provider.set_browser(make_browser("deck-b", 3))

        frame = provider.get_slide_frame(3)

        self.assertEqual(frame.deck_id, "deck-b")
        self.assertEqual(frame.slide_id, 3)

    def test_clear_removes_active_uploaded_deck(self):
        provider = self.make_provider()
        provider.set_browser(make_browser())
        provider.clear()

        with self.assertRaisesRegex(RuntimeError, "No uploaded deck is active"):
            provider.get_slide_frame(2)


if __name__ == "__main__":
    unittest.main()
