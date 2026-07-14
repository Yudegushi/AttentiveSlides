"""Tests for Qwen Omni Realtime endpoint selection."""

from __future__ import annotations

import os
from unittest.mock import patch
import unittest
from urllib.parse import (
    parse_qs,
    urlsplit,
)

from modules.realtime.bailian_omni_realtime_client import (
    BailianOmniRealtimeClient,
)


class TestRealtimeEndpointResolution(
    unittest.TestCase
):
    def client(
        self,
        *,
        workspace_id: str | None,
        region: str = "beijing",
    ) -> BailianOmniRealtimeClient:
        return BailianOmniRealtimeClient(
            api_key="test-key",
            workspace_id=workspace_id,
            model=(
                "qwen3.5-omni-"
                "plus-realtime"
            ),
            region=region,
        )

    def assert_model_query(
        self,
        endpoint: str,
    ) -> None:
        query = parse_qs(
            urlsplit(
                endpoint
            ).query
        )

        self.assertEqual(
            query.get(
                "model"
            ),
            [
                (
                    "qwen3.5-omni-"
                    "plus-realtime"
                )
            ],
        )

    def test_explicit_base_url_has_priority(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                (
                    "ATTENTIVE_"
                    "REALTIME_BASE_URL"
                ): (
                    "wss://dashscope."
                    "aliyuncs.com"
                    "/api-ws/v1/realtime"
                )
            },
            clear=False,
        ):
            endpoint = self.client(
                workspace_id=(
                    "valid-workspace"
                ),
            ).endpoint()

        parts = urlsplit(
            endpoint
        )

        self.assertEqual(
            parts.hostname,
            "dashscope.aliyuncs.com",
        )

        self.assert_model_query(
            endpoint
        )

    def test_placeholder_workspace_uses_beijing_fallback(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                (
                    "ATTENTIVE_"
                    "REALTIME_BASE_URL"
                ): "",
            },
            clear=False,
        ):
            endpoint = self.client(
                workspace_id=(
                    "<YOUR_WORKSPACE_ID>"
                ),
            ).endpoint()

        self.assertEqual(
            urlsplit(
                endpoint
            ).hostname,
            "dashscope.aliyuncs.com",
        )

    def test_missing_workspace_uses_singapore_fallback(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                (
                    "ATTENTIVE_"
                    "REALTIME_BASE_URL"
                ): "",
            },
            clear=False,
        ):
            endpoint = self.client(
                workspace_id=None,
                region="singapore",
            ).endpoint()

        self.assertEqual(
            urlsplit(
                endpoint
            ).hostname,
            (
                "dashscope-intl."
                "aliyuncs.com"
            ),
        )

    def test_valid_workspace_uses_dedicated_domain(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                (
                    "ATTENTIVE_"
                    "REALTIME_BASE_URL"
                ): "",
            },
            clear=False,
        ):
            endpoint = self.client(
                workspace_id=(
                    "workspace-123"
                ),
            ).endpoint()

        self.assertEqual(
            urlsplit(
                endpoint
            ).hostname,
            (
                "workspace-123."
                "cn-beijing."
                "maas.aliyuncs.com"
            ),
        )

    def test_non_wss_override_is_rejected(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                (
                    "ATTENTIVE_"
                    "REALTIME_BASE_URL"
                ): (
                    "https://dashscope."
                    "aliyuncs.com"
                    "/api-ws/v1/realtime"
                )
            },
            clear=False,
        ):
            with self.assertRaises(
                RuntimeError
            ):
                self.client(
                    workspace_id=None
                ).endpoint()


if __name__ == "__main__":
    unittest.main()
