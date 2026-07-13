"""One isolated Streamlit AppTest interaction scenario.

Do not run this file directly from an interactive terminal.
Use scripts/smoke_test_main_ui_interactions.py instead.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


# Configure native libraries before importing Streamlit.
os.environ.pop(
    "DASHSCOPE_API_KEY",
    None,
)

os.environ.update(
    {
        "ATTENTIVE_ENABLE_OCR": "0",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONFAULTHANDLER": "1",
        "MPLBACKEND": "Agg",
    }
)

try:
    import resource

    resource.setrlimit(
        resource.RLIMIT_CORE,
        (
            0,
            0,
        ),
    )
except (
    ImportError,
    OSError,
    ValueError,
):
    pass


from streamlit.testing.v1 import AppTest


ROOT = Path(
    __file__
).resolve().parents[1]

APP_PATH = (
    ROOT
    / "apps"
    / "streamlit_attentive_slides.py"
)


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def app_exception_messages(
    app: AppTest,
) -> list[str]:
    return [
        str(
            getattr(
                exception,
                "message",
                exception,
            )
        )
        for exception in app.exception
    ]


def get_widget(
    block: Any,
    widget_type: str,
    key: str,
) -> Any | None:
    collection = getattr(
        block,
        widget_type,
    )

    try:
        return collection(
            key=key
        )
    except Exception:
        matches = [
            widget
            for widget in collection
            if getattr(
                widget,
                "key",
                None,
            )
            == key
        ]

        if len(matches) == 1:
            return matches[0]

        return None


def require_widget(
    block: Any,
    widget_type: str,
    key: str,
) -> Any:
    widget = get_widget(
        block,
        widget_type,
        key,
    )

    if widget is not None:
        return widget

    collection = getattr(
        block,
        widget_type,
    )

    available = [
        {
            "key": getattr(
                item,
                "key",
                None,
            ),
            "label": getattr(
                item,
                "label",
                None,
            ),
        }
        for item in collection
    ]

    raise LookupError(
        f"Missing {widget_type} with key "
        f"{key!r}. Available: {available}"
    )


def find_button_by_label(
    app: AppTest,
    label: str,
) -> Any | None:
    matches = [
        button
        for button in app.button
        if getattr(
            button,
            "label",
            None,
        )
        == label
    ]

    if len(matches) == 1:
        return matches[0]

    return None


def run_step(
    app: AppTest,
    completed_steps: list[str],
    step: str,
) -> None:
    app.run(
        timeout=60
    )

    exceptions = app_exception_messages(
        app
    )

    if exceptions:
        raise AssertionError(
            f"{step}: Streamlit exceptions: "
            f"{exceptions}"
        )

    completed_steps.append(
        step
    )


def create_app() -> tuple[
    AppTest,
    list[str],
]:
    app = AppTest.from_file(
        str(APP_PATH)
    )

    completed_steps: list[str] = []

    run_step(
        app,
        completed_steps,
        "initial_render",
    )

    return (
        app,
        completed_steps,
    )


def run_sidebar_scenario() -> dict[str, Any]:
    app, completed = create_app()

    for index in range(2):
        require_widget(
            app.sidebar,
            "checkbox",
            "main_cloud_text_allowed",
        ).uncheck()

        run_step(
            app,
            completed,
            f"cloud_off_{index}",
        )

        require_widget(
            app.sidebar,
            "checkbox",
            "main_cloud_text_allowed",
        ).check()

        run_step(
            app,
            completed,
            f"cloud_on_{index}",
        )

    for index in range(2):
        require_widget(
            app.sidebar,
            "checkbox",
            "main_history_enabled",
        ).uncheck()

        run_step(
            app,
            completed,
            f"history_off_{index}",
        )

        slider = require_widget(
            app.sidebar,
            "slider",
            "main_history_max_items",
        )

        if not bool(
            getattr(
                slider,
                "disabled",
                False,
            )
        ):
            raise AssertionError(
                "History slider must be disabled "
                "when conversation history is disabled."
            )

        require_widget(
            app.sidebar,
            "checkbox",
            "main_history_enabled",
        ).check()

        run_step(
            app,
            completed,
            f"history_on_{index}",
        )

    for index, value in enumerate(
        (
            1,
            4,
            2,
            3,
            1,
            4,
        )
    ):
        require_widget(
            app.sidebar,
            "slider",
            "main_history_max_items",
        ).set_value(value)

        run_step(
            app,
            completed,
            f"history_limit_{index}_{value}",
        )

    return {
        "completed_steps": completed,
        "final_state": {
            "cloud_text_allowed": (
                app.session_state[
                    "main_cloud_text_allowed"
                ]
            ),
            "history_enabled": (
                app.session_state[
                    "main_history_enabled"
                ]
            ),
            "history_max_items": (
                app.session_state[
                    "main_history_max_items"
                ]
            ),
        },
    }


def run_overlay_scenario() -> dict[str, Any]:
    app, completed = create_app()

    for index in range(3):
        require_widget(
            app,
            "checkbox",
            "main_show_aoi_overlay",
        ).uncheck()

        run_step(
            app,
            completed,
            f"overlay_off_{index}",
        )

        require_widget(
            app,
            "checkbox",
            "main_show_aoi_overlay",
        ).check()

        run_step(
            app,
            completed,
            f"overlay_on_{index}",
        )

    return {
        "completed_steps": completed,
        "final_state": {
            "show_aoi_overlay": (
                app.session_state[
                    "main_show_aoi_overlay"
                ]
            ),
        },
    }


def run_manual_region_scenario() -> dict[str, Any]:
    app, completed = create_app()

    require_widget(
        app,
        "radio",
        "main_target_scope",
    ).set_value(
        "Manual region"
    )

    run_step(
        app,
        completed,
        "manual_region_mode",
    )

    ranges = (
        (
            (0.10, 0.90),
            (0.10, 0.90),
        ),
        (
            (0.20, 0.75),
            (0.15, 0.80),
        ),
        (
            (0.30, 0.65),
            (0.25, 0.70),
        ),
    )

    for index, (
        x_range,
        y_range,
    ) in enumerate(ranges):
        require_widget(
            app,
            "slider",
            "main_region_x_range",
        ).set_range(
            *x_range
        )

        run_step(
            app,
            completed,
            f"horizontal_range_{index}",
        )

        require_widget(
            app,
            "slider",
            "main_region_y_range",
        ).set_range(
            *y_range
        )

        run_step(
            app,
            completed,
            f"vertical_range_{index}",
        )

    for index in range(2):
        require_widget(
            app,
            "button",
            "main_apply_region_button",
        ).click()

        run_step(
            app,
            completed,
            f"apply_region_{index}",
        )

    for index in range(2):
        require_widget(
            app,
            "button",
            "main_clear_region_button",
        ).click()

        run_step(
            app,
            completed,
            f"clear_region_{index}",
        )

    require_widget(
        app,
        "radio",
        "main_target_scope",
    ).set_value(
        "Whole slide"
    )

    run_step(
        app,
        completed,
        "whole_slide_mode",
    )

    require_widget(
        app,
        "radio",
        "main_target_scope",
    ).set_value(
        "Manual region"
    )

    run_step(
        app,
        completed,
        "manual_region_mode_again",
    )

    return {
        "completed_steps": completed,
        "final_state": {
            "target_scope": (
                app.session_state[
                    "main_target_scope"
                ]
            ),
            "manual_region_active": (
                app.session_state[
                    "main_manual_region_active"
                ]
            ),
        },
    }


def run_intent_scenario() -> dict[str, Any]:
    app, completed = create_app()

    for index, command in enumerate(
        (
            "explain this",
            "summarize this",
            "",
            "explain this",
        )
    ):
        require_widget(
            app,
            "text_area",
            "main_typed_command",
        ).set_value(
            command
        )

        run_step(
            app,
            completed,
            f"typed_command_{index}",
        )

    quick_labels = (
        "Explain",
        "Summarize",
        "Simplify",
        "Step by step",
        "Compare",
        "Quiz",
    )

    skipped: list[str] = []

    for label in quick_labels:
        button = find_button_by_label(
            app,
            label,
        )

        if button is None:
            skipped.append(
                label
            )
            continue

        button.click()

        run_step(
            app,
            completed,
            f"quick_{label}_first",
        )

        repeated = find_button_by_label(
            app,
            label,
        )

        if repeated is None:
            raise AssertionError(
                f"Quick action disappeared "
                f"after one click: {label}"
            )

        repeated.click()

        run_step(
            app,
            completed,
            f"quick_{label}_second",
        )

    return {
        "completed_steps": completed,
        "skipped": skipped,
        "final_state": {
            "typed_command": (
                app.session_state[
                    "main_typed_command"
                ]
            ),
            "intent_source": (
                app.session_state[
                    "main_intent_source"
                ]
            ),
        },
    }


def run_reset_scenario() -> dict[str, Any]:
    app, completed = create_app()

    for index in range(4):
        require_widget(
            app,
            "button",
            "main_reset_turn_button",
        ).click()

        run_step(
            app,
            completed,
            f"reset_turn_{index}",
        )

    clear_conversation = get_widget(
        app,
        "button",
        "main_clear_conversation_button",
    )

    if (
        clear_conversation is not None
        and not bool(
            getattr(
                clear_conversation,
                "disabled",
                False,
            )
        )
    ):
        clear_conversation.click()

        run_step(
            app,
            completed,
            "clear_conversation",
        )

    next_button = get_widget(
        app,
        "button",
        "main_next_slide_button",
    )

    if (
        next_button is not None
        and not bool(
            getattr(
                next_button,
                "disabled",
                False,
            )
        )
    ):
        next_button.click()

        run_step(
            app,
            completed,
            "next_slide",
        )

        previous_button = get_widget(
            app,
            "button",
            "main_previous_slide_button",
        )

        if (
            previous_button is not None
            and not bool(
                getattr(
                    previous_button,
                    "disabled",
                    False,
                )
            )
        ):
            previous_button.click()

            run_step(
                app,
                completed,
                "previous_slide",
            )

    return {
        "completed_steps": completed,
        "final_state": {
            "conversation_turn_count": len(
                app.session_state[
                    "main_conversation_turns"
                ]
            ),
            "typed_command": (
                app.session_state[
                    "main_typed_command"
                ]
            ),
        },
    }


SCENARIOS = {
    "sidebar": run_sidebar_scenario,
    "overlay": run_overlay_scenario,
    "manual_region": (
        run_manual_region_scenario
    ),
    "intent": run_intent_scenario,
    "reset": run_reset_scenario,
}


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--scenario",
        required=True,
        choices=sorted(
            SCENARIOS
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    arguments = parser.parse_args()

    output_path = Path(
        arguments.output
    )

    try:
        scenario_payload = (
            SCENARIOS[
                arguments.scenario
            ]()
        )

        payload = {
            "passed": True,
            "scenario": (
                arguments.scenario
            ),
            **scenario_payload,
            "exceptions": [],
        }

    except BaseException as exc:
        payload = {
            "passed": False,
            "scenario": (
                arguments.scenario
            ),
            "error_type": (
                type(exc).__name__
            ),
            "error": str(exc),
            "traceback": (
                traceback.format_exc()
            ),
        }

        write_json(
            output_path,
            payload,
        )

        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
            flush=True,
        )

        raise

    write_json(
        output_path,
        payload,
    )

    print(
        f"SCENARIO_PASS: "
        f"{arguments.scenario}",
        flush=True,
    )


if __name__ == "__main__":
    main()
