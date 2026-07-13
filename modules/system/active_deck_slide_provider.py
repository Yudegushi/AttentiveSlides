"""Expose the active uploaded deck through the live SlideProvider contract."""

from __future__ import annotations

from threading import RLock

from modules.system.adapters import SlideFrame
from modules.system.uploaded_deck_service import UploadedDeckBrowser


class ActiveDeckSlideProvider:
    def __init__(self) -> None:
        self._lock = RLock()
        self._browser: UploadedDeckBrowser | None = None

    def set_browser(self, browser: UploadedDeckBrowser) -> None:
        with self._lock:
            self._browser = browser

    def clear(self) -> None:
        with self._lock:
            self._browser = None

    def get_slide_frame(self, slide_id: int) -> SlideFrame:
        with self._lock:
            browser = self._browser
        if browser is None:
            raise RuntimeError("No uploaded deck is active.")
        slide = browser.get_slide(slide_id)
        return SlideFrame(
            deck_id=browser.deck_id,
            slide_id=slide.slide_id,
            aois=list(slide.aois),
            slide_text=slide.slide_text,
            neighbor_slide_text=slide.neighbor_slide_text,
            slide_image_path=slide.image_path,
        )
