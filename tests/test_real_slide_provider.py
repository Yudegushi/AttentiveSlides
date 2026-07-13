import tempfile
import unittest
from pathlib import Path

import fitz

from modules.common.schemas import GazePrediction, LearningState, Transcript
from modules.system.adapters import (
    ProviderBackedDeckStore,
    SensingFrame,
    build_pipeline_input_bundle,
    run_interaction_from_bundle,
)

try:
    from modules.system.real_slide_provider import RealSlideProvider
except ImportError:
    RealSlideProvider = None


def make_deck(path: Path, page_count: int = 3) -> None:
    document = fitz.open()
    concepts = ("First concept", "Second concept", "Third concept")
    for number, body in enumerate(concepts[:page_count], start=1):
        page = document.new_page()
        page.insert_text((72, 72), f"Slide {number} title", fontsize=22)
        page.insert_text((72, 180), body, fontsize=16)
        page.insert_text((72, 770), f"Footer {number}", fontsize=9)
    document.save(path)
    document.close()


class StaticTranscriptProvider:
    def get_transcript(self) -> Transcript:
        return Transcript("解释这个")


class StaticSensingProvider:
    def __init__(self, target_aoi_id: str) -> None:
        self.target_aoi_id = target_aoi_id

    def get_sensing_frame(self, slide_id: int) -> SensingFrame:
        return SensingFrame(
            gaze_prediction=GazePrediction(
                slide_id=slide_id,
                gaze_grid="middle_center",
                predicted_aoi_id=self.target_aoi_id,
                confidence=0.76,
                stable_duration_sec=2.0,
            ),
            learning_state=LearningState(),
        )


class MissingDeckIdProvider:
    def __init__(self) -> None:
        self.requested_slide_ids: list[int] = []

    def get_slide_frame(self, slide_id: int):
        self.requested_slide_ids.append(slide_id)
        raise AssertionError("deck_id must not trigger a slide lookup")


class RealSlideProviderTest(unittest.TestCase):
    def test_loads_pdf_with_explicit_deck_id_neighbors_and_canonical_aois(self):
        self.assertIsNotNone(RealSlideProvider)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "deck.pdf"
            make_deck(pdf_path)
            provider = RealSlideProvider(data_dir=root / "data")

            deck_id = provider.load_deck(pdf_path)
            first = provider.get_slide_frame(1)
            last = provider.get_slide_frame(3)

            self.assertEqual(provider.deck_id, deck_id)
            self.assertEqual(first.deck_id, deck_id)
            self.assertIn("Second concept", first.neighbor_slide_text)
            self.assertNotIn("Third concept", first.neighbor_slide_text)
            self.assertIn("Second concept", last.neighbor_slide_text)
            self.assertNotIn("First concept", last.neighbor_slide_text)
            self.assertEqual(first.aois[-1].aoi_id, "whole_slide")
            self.assertTrue(any(aoi.text == "First concept" for aoi in first.aois))
            self.assertFalse(any(aoi.type == "footer" for aoi in first.aois))
            self.assertTrue(
                all(0.0 <= value <= 1.0 for aoi in first.aois for value in aoi.bbox)
            )

    def test_loads_uploaded_bytes_for_single_and_two_page_decks(self):
        self.assertIsNotNone(RealSlideProvider)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for page_count in (1, 2):
                with self.subTest(page_count=page_count):
                    pdf_path = root / f"deck-{page_count}.pdf"
                    make_deck(pdf_path, page_count=page_count)
                    provider = RealSlideProvider(data_dir=root / f"data-{page_count}")

                    provider.load_deck(pdf_path.read_bytes(), filename=pdf_path.name)
                    first = provider.get_slide_frame(1)

                    self.assertEqual(provider.page_count, page_count)
                    if page_count == 1:
                        self.assertEqual(first.neighbor_slide_text, "")
                    else:
                        self.assertIn("Second concept", first.neighbor_slide_text)

    def test_repeated_frames_have_deterministic_aoi_ordering(self):
        self.assertIsNotNone(RealSlideProvider)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "deck.pdf"
            make_deck(pdf_path)
            provider = RealSlideProvider(data_dir=root / "data")
            provider.load_deck(pdf_path)

            first = provider.get_slide_frame(2)
            repeated = provider.get_slide_frame(2)

            self.assertEqual(first.aois, repeated.aois)
            self.assertEqual(
                [aoi.aoi_id for aoi in first.aois],
                [aoi.aoi_id for aoi in repeated.aois],
            )

    def test_real_provider_runs_existing_confirmation_gate(self):
        self.assertIsNotNone(RealSlideProvider)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "deck.pdf"
            make_deck(pdf_path)
            provider = RealSlideProvider(data_dir=root / "data")
            provider.load_deck(pdf_path)
            target = next(
                aoi.aoi_id
                for aoi in provider.get_slide_frame(2).aois
                if aoi.aoi_id != "whole_slide"
            )

            bundle = build_pipeline_input_bundle(
                slide_provider=provider,
                transcript_provider=StaticTranscriptProvider(),
                sensing_provider=StaticSensingProvider(target),
                slide_id=2,
            )
            result = run_interaction_from_bundle(bundle)

            self.assertEqual(result.resolved_query.confirmation_mode, "confirm_one")
            self.assertEqual(result.tutor_response.response_mode, "pending_confirmation")

    def test_deck_store_never_probes_fixed_slide_to_find_deck_id(self):
        provider = MissingDeckIdProvider()
        store = ProviderBackedDeckStore(provider)

        with self.assertRaisesRegex(RuntimeError, "explicit deck_id"):
            _ = store.deck_id

        self.assertEqual(provider.requested_slide_ids, [])


if __name__ == "__main__":
    unittest.main()
