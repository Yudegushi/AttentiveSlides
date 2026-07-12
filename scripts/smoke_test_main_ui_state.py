"""Recorded deterministic smoke test for Main UI state."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(
    __file__
).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPOSITORY_ROOT),
    )

from llm_smoke_common import (
    base_record,
    write_record,
)
from modules.system.main_ui_state import (
    ManifestDeckBrowser,
    build_main_ui_view_model,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    manifest_path = (
        REPOSITORY_ROOT
        / "data"
        / "mock_deck"
        / "mock_aoi_manifest.json"
    )

    browser = ManifestDeckBrowser(
        manifest_path,
        asset_root=REPOSITORY_ROOT,
    )

    active_slide_id = browser.slide_ids[0]

    view = build_main_ui_view_model(
        browser,
        active_slide_id=active_slide_id,
        cloud_text_allowed=True,
    )

    checks = {
        "deck_loaded": bool(
            view.deck_id.strip()
        ),
        "slide_available": (
            view.total_slides >= 1
        ),
        "active_slide_valid": (
            view.active_slide_id
            in view.slide_ids
        ),
        "slide_object_available": (
            view.active_slide.slide_id
            == view.active_slide_id
        ),
        "manual_mode": (
            view.privacy.interaction_mode
            == "manual"
        ),
        "camera_disabled": (
            not view.privacy.camera_enabled
        ),
        "microphone_disabled": (
            not view.privacy.microphone_enabled
        ),
        "no_raw_biometrics": (
            not view.privacy
            .raw_biometrics_collected
        ),
        "cloud_llm_not_called": (
            not view.privacy.cloud_llm_called
        ),
        "cloud_permission_preserved": (
            view.privacy
            .selected_slide_text_cloud_allowed
        ),
    }

    payload = base_record(
        "main_ui_shell_state_smoke"
    )

    payload.update(
        {
            "passed": all(checks.values()),
            "checks": checks,
            "view_model": view.to_dict(),
        }
    )

    write_record(
        arguments.output,
        payload,
    )

    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
