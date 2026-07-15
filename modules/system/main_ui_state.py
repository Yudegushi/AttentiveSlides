"""Deck browsing and stable view state for the AttentiveSlides Main UI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from collections.abc import Callable, MutableMapping
from typing import Any

from modules.common.schemas import AOI, VisualContextItem


@dataclass(frozen=True)
class MainUISlide:
    """One slide prepared for the Main UI."""

    slide_id: int
    slide_text: str
    neighbor_slide_text: str
    aois: tuple[AOI, ...]
    image_path: str | None = None
    aoi_profile: str = "deterministic"
    visual_context: tuple[VisualContextItem, ...] = ()

    @property
    def image_available(self) -> bool:
        return (
            self.image_path is not None
            and Path(self.image_path).is_file()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "slide_id": self.slide_id,
            "slide_text": self.slide_text,
            "neighbor_slide_text": (
                self.neighbor_slide_text
            ),
            "image_path": self.image_path,
            "image_available": self.image_available,
            "aoi_profile": self.aoi_profile,
            "visual_context": [
                item.to_dict()
                for item in self.visual_context
            ],
            "aois": [
                asdict(aoi)
                for aoi in self.aois
            ],
        }


@dataclass(frozen=True)
class PrivacyStatus:
    """Current modality and data-use state."""

    interaction_mode: str
    camera_enabled: bool
    microphone_enabled: bool
    raw_biometrics_collected: bool
    cloud_llm_called: bool
    selected_slide_text_cloud_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MainUIViewModel:
    """Serializable state consumed by the Streamlit shell."""

    deck_id: str
    deck_title: str
    slide_ids: tuple[int, ...]
    active_slide_id: int
    active_slide_index: int
    total_slides: int
    can_go_previous: bool
    can_go_next: bool
    active_slide: MainUISlide
    privacy: PrivacyStatus

    def to_dict(self) -> dict[str, Any]:
        return {
            "deck_id": self.deck_id,
            "deck_title": self.deck_title,
            "slide_ids": list(self.slide_ids),
            "active_slide_id": self.active_slide_id,
            "active_slide_index": (
                self.active_slide_index
            ),
            "total_slides": self.total_slides,
            "can_go_previous": self.can_go_previous,
            "can_go_next": self.can_go_next,
            "active_slide": (
                self.active_slide.to_dict()
            ),
            "privacy": self.privacy.to_dict(),
        }



def normalize_main_slide_width_percent(value: object) -> int:
    """Clamp and snap the persisted slide width preference."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 100
    snapped = int(round(numeric / 5.0) * 5)
    return max(50, min(100, snapped))


def build_main_turn_defaults() -> dict[str, Any]:
    """Return fresh defaults for one manual tutoring turn."""
    return {
        "main_target_scope": "Whole slide",
        "main_typed_command": "",
        "main_manual_bbox": None,
        "main_region_x_range": (0.10, 0.90),
        "main_region_y_range": (0.10, 0.90),
        "main_manual_region_active": False,
        "main_widget_error": None,
        "main_selected_aoi_ids": [],
        "main_selection_matches": [],
        "main_selection_text": "",
        "main_selection_error": None,
        "main_intent_source": None,
        "main_explicit_intent": None,
        "main_intent_result": None,
        "main_intent_error": None,
        "main_confirmation_target_choice": None,
        "main_confirmation_source": None,
        "main_confirmed_aoi_id": None,
        "main_corrected_from_aoi_id": None,
        "main_confirmed_interaction": None,
        "main_confirmation_error": None,
        "main_confirmed": False,
        "main_tutor_result": None,
        "main_tutor_context": None,
        "main_last_generated_interaction_id": None,
        "main_tutor_error": None,
        "main_xai_result": None,
    }


def build_main_live_defaults() -> dict[str, Any]:
    """Return the small set of Live-mode session defaults."""
    return {
        "main_interaction_mode": "Manual",
        "main_live_master_enabled": False,
        "main_confirmation_policy": "Always confirm",
        "main_auto_confirm_threshold": 0.80,
        "main_live_proposal": None,
        "main_live_original_transcript": None,
        "main_live_predicted_aoi_id": None,
        "main_live_layout_revision": None,
        "main_logged_interaction_ids": [],
    }


def reset_main_turn_state(
    state: MutableMapping[str, Any],
) -> None:
    """Reset turn-specific state while preserving session data."""
    for key, value in build_main_turn_defaults().items():
        state[key] = value


def reset_main_live_turn_state(
    state: MutableMapping[str, Any],
) -> None:
    """Clear one Live proposal while retaining user preferences."""
    reset_main_turn_state(state)
    for key in (
        "main_live_proposal",
        "main_live_original_transcript",
        "main_live_predicted_aoi_id",
        "main_live_layout_revision",
    ):
        state[key] = None


def write_main_interaction_once(
    logged_interaction_ids: list[str],
    *,
    interaction_id: str,
    payload: dict[str, Any],
    write: Callable[[dict[str, Any]], None],
) -> bool:
    """Write before marking an interaction ID as durably logged."""
    if interaction_id in logged_interaction_ids:
        return False
    write(payload)
    logged_interaction_ids.append(interaction_id)
    return True


def build_main_conversation_defaults() -> dict[str, Any]:
    """Return session-level conversation defaults."""
    return {
        "main_conversation_turns": [],
        "main_conversation_deck_id": None,
        "main_history_enabled": True,
        "main_history_max_items": 4,
        "main_conversation_error": None,
    }


def reset_main_conversation_state(
    state: MutableMapping[str, Any],
    *,
    deck_id: str | None = None,
) -> None:
    """Clear turns while preserving history preferences."""
    state["main_conversation_turns"] = []
    state["main_conversation_deck_id"] = deck_id
    state["main_conversation_error"] = None


class ManifestDeckBrowser:
    """Read deck metadata and provide deterministic navigation."""

    def __init__(
        self,
        manifest_path: str | Path,
        *,
        asset_root: str | Path | None = None,
    ) -> None:
        self.manifest_path = Path(
            manifest_path
        ).resolve()

        self.asset_root = Path(
            asset_root or Path.cwd()
        ).resolve()

        payload = self._load_manifest()

        self.deck_id = self._required_text(
            payload,
            "deck_id",
        )

        self.title = str(
            payload.get("title")
            or self.deck_id
        )

        slide_payloads = payload.get("slides")

        if not isinstance(slide_payloads, list):
            raise ValueError(
                "Manifest slides must be a list."
            )

        if not slide_payloads:
            raise ValueError(
                "Manifest must contain at least one slide."
            )

        slides: dict[int, MainUISlide] = {}

        for item in slide_payloads:
            slide = self._parse_slide(item)

            if slide.slide_id in slides:
                raise ValueError(
                    "Duplicate slide ID in manifest: "
                    f"{slide.slide_id}"
                )

            slides[slide.slide_id] = slide

        self._slides = slides
        self._slide_ids = tuple(slides.keys())

    @property
    def slide_ids(self) -> tuple[int, ...]:
        return self._slide_ids

    def get_slide(
        self,
        slide_id: int,
    ) -> MainUISlide:
        try:
            return self._slides[slide_id]
        except KeyError as exc:
            raise KeyError(
                f"Slide {slide_id} is not in deck "
                f"{self.deck_id!r}."
            ) from exc

    def slide_index(
        self,
        slide_id: int,
    ) -> int:
        try:
            return self._slide_ids.index(slide_id)
        except ValueError as exc:
            raise KeyError(
                f"Slide {slide_id} is not in deck "
                f"{self.deck_id!r}."
            ) from exc

    def previous_slide_id(
        self,
        slide_id: int,
    ) -> int | None:
        index = self.slide_index(slide_id)

        if index == 0:
            return None

        return self._slide_ids[index - 1]

    def next_slide_id(
        self,
        slide_id: int,
    ) -> int | None:
        index = self.slide_index(slide_id)

        if index >= len(self._slide_ids) - 1:
            return None

        return self._slide_ids[index + 1]

    def _load_manifest(
        self,
    ) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            raise FileNotFoundError(
                f"Deck manifest not found: "
                f"{self.manifest_path}"
            )

        with self.manifest_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)

        if not isinstance(payload, dict):
            raise ValueError(
                "Deck manifest root must be an object."
            )

        return payload

    def _parse_slide(
        self,
        item: Any,
    ) -> MainUISlide:
        if not isinstance(item, dict):
            raise ValueError(
                "Each slide manifest item must "
                "be an object."
            )

        slide_id = int(item["slide_id"])

        if slide_id < 0:
            raise ValueError(
                "slide_id must be non-negative."
            )

        aoi_payloads = item.get("aois", [])

        if not isinstance(aoi_payloads, list):
            raise ValueError(
                "Slide aois must be a list."
            )

        aois = tuple(
            AOI(**aoi_payload)
            for aoi_payload in aoi_payloads
        )

        image_value = item.get(
            "slide_image_path",
            item.get("image_path"),
        )

        image_path = self._resolve_asset_path(
            image_value
        )

        return MainUISlide(
            slide_id=slide_id,
            slide_text=str(
                item.get("ocr_text", "")
            ),
            neighbor_slide_text=str(
                item.get(
                    "neighbor_slide_text",
                    "",
                )
            ),
            aois=aois,
            image_path=image_path,
        )

    def _resolve_asset_path(
        self,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        raw_path = Path(str(value))

        if raw_path.is_absolute():
            return str(raw_path.resolve())

        return str(
            (
                self.asset_root
                / raw_path
            ).resolve()
        )

    @staticmethod
    def _required_text(
        payload: dict[str, Any],
        key: str,
    ) -> str:
        value = payload.get(key)

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                f"Manifest {key} must be "
                "a non-blank string."
            )

        return value.strip()


def build_main_ui_view_model(
    browser: ManifestDeckBrowser,
    *,
    active_slide_id: int,
    cloud_text_allowed: bool,
) -> MainUIViewModel:
    """Build the stable Main UI view model."""
    active_slide = browser.get_slide(
        active_slide_id
    )

    active_index = browser.slide_index(
        active_slide_id
    )

    return MainUIViewModel(
        deck_id=browser.deck_id,
        deck_title=browser.title,
        slide_ids=browser.slide_ids,
        active_slide_id=active_slide_id,
        active_slide_index=active_index,
        total_slides=len(browser.slide_ids),
        can_go_previous=(
            browser.previous_slide_id(
                active_slide_id
            )
            is not None
        ),
        can_go_next=(
            browser.next_slide_id(
                active_slide_id
            )
            is not None
        ),
        active_slide=active_slide,
        privacy=PrivacyStatus(
            interaction_mode="manual",
            camera_enabled=False,
            microphone_enabled=False,
            raw_biometrics_collected=False,
            cloud_llm_called=False,
            selected_slide_text_cloud_allowed=(
                cloud_text_allowed
            ),
        ),
    )
