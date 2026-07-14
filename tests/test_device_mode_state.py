"""Tests for sidebar device and interaction mode."""

from __future__ import annotations

import unittest

from modules.realtime.realtime_contracts import (
    DeviceState,
)
from modules.system.device_mode_state import (
    derive_interaction_mode,
    microphone_enabled_state,
)


class TestDeviceModeState(
    unittest.TestCase
):
    def test_all_device_combinations(
        self,
    ) -> None:
        cases = (
            (
                False,
                False,
                "manual",
            ),
            (
                True,
                False,
                "hybrid",
            ),
            (
                False,
                True,
                "hybrid",
            ),
            (
                True,
                True,
                "hybrid",
            ),
        )

        for (
            camera,
            microphone,
            expected,
        ) in cases:
            with self.subTest(
                camera=camera,
                microphone=microphone,
            ):
                self.assertEqual(
                    derive_interaction_mode(
                        camera_enabled=(
                            camera
                        ),
                        microphone_enabled=(
                            microphone
                        ),
                    ),
                    expected,
                )

    def test_denied_permission_keeps_microphone_off(
        self,
    ) -> None:
        state = DeviceState(
            camera_enabled=False,
            microphone_enabled=False,
            microphone_permission=(
                "unknown"
            ),
        )

        updated = (
            microphone_enabled_state(
                state,
                enabled=True,
                permission="denied",
            )
        )

        self.assertFalse(
            updated.microphone_enabled
        )

        self.assertEqual(
            updated.interaction_mode,
            "manual",
        )


if __name__ == "__main__":
    unittest.main()
