from __future__ import annotations

import json
from pathlib import Path
import tempfile
from threading import Event, Thread, current_thread
import unittest
from unittest.mock import patch

from modules.slide.aoi_manager import AOI, AOIManager, SlideAOIData


def slide_data(slide_id: int) -> SlideAOIData:
    return SlideAOIData(
        slide_id=slide_id,
        slide_image_path=f"slide-{slide_id}.png",
        ocr_text=f"Slide {slide_id}",
        aois=[AOI("whole_slide", [0.0, 0.0, 1.0, 1.0], "whole_slide")],
        text_source="pdf_text",
        auto_aoi_method="pdf_text_semantic",
    )


class AOIManagerConcurrencyTest(unittest.TestCase):
    def test_manifest_writes_are_serialized_across_live_threads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = AOIManager(data_dir=directory)
            first_dump_started = Event()
            release_first_dump = Event()
            second_dump_entered = Event()
            errors: list[BaseException] = []
            real_dump = json.dump

            def controlled_dump(payload, file, **kwargs):
                if current_thread().name == "first-aoi-writer":
                    first_dump_started.set()
                    release_first_dump.wait(timeout=2.0)
                else:
                    second_dump_entered.set()
                return real_dump(payload, file, **kwargs)

            def save(slide_id: int) -> None:
                try:
                    manager.save_slide_data("deck", slide_data(slide_id))
                except BaseException as exc:
                    errors.append(exc)

            with patch("modules.slide.aoi_manager.json.dump", side_effect=controlled_dump):
                first = Thread(target=save, args=(1,), name="first-aoi-writer")
                second = Thread(target=save, args=(2,), name="second-aoi-writer")
                first.start()
                self.assertTrue(first_dump_started.wait(timeout=1.0))
                second.start()
                concurrent_dump = second_dump_entered.wait(timeout=0.2)
                release_first_dump.set()
                first.join(timeout=2.0)
                second.join(timeout=2.0)

            self.assertFalse(
                concurrent_dump,
                "a second live thread entered manifest serialization concurrently",
            )
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(errors, [])
            persisted = json.loads(Path(manager.manifest_file).read_text(encoding="utf-8"))
            self.assertEqual(set(persisted), {"deck:1", "deck:2"})


if __name__ == "__main__":
    unittest.main()
