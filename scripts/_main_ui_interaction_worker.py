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
        "ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST": "1",
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

os.environ["ATTENTIVE_DISABLE_CANVAS_FOR_APPTEST"] = "1"

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

    if (
        app.session_state[
            "main_history_max_items"
        ]
        != 4
    ):
        raise AssertionError(
            "History limit must default to four."
        )

    history_limit_sliders = [
        slider
        for slider in app.sidebar.slider
        if getattr(
            slider,
            "key",
            None,
        )
        == "main_history_max_items"
    ]

    if history_limit_sliders:
        raise AssertionError(
            "The recent-turn history slider "
            "should not be rendered."
        )

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

        if (
            app.session_state[
                "main_history_max_items"
            ]
            != 4
        ):
            raise AssertionError(
                "Cloud permission changed "
                "the history limit."
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

        if (
            app.session_state[
                "main_history_max_items"
            ]
            != 4
        ):
            raise AssertionError(
                "Disabling history changed "
                "the fixed limit."
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

        if (
            app.session_state[
                "main_history_max_items"
            ]
            != 4
        ):
            raise AssertionError(
                "Enabling history changed "
                "the fixed limit."
            )

    history_limit_sliders = [
        slider
        for slider in app.sidebar.slider
        if getattr(
            slider,
            "key",
            None,
        )
        == "main_history_max_items"
    ]

    if history_limit_sliders:
        raise AssertionError(
            "The history slider reappeared "
            "after a rerun."
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



def session_state_value(
    app,
    key: str,
    default=None,
):
    """Read AppTest session state without dict.get()."""

    try:
        return app.session_state[
            key
        ]

    except (
        KeyError,
        AttributeError,
    ):
        return default


def run_manual_region_scenario() -> dict[str, Any]:
    app, completed = create_app()

    option_snapshots: list[
        list[str]
    ] = []

    selection_records: list[
        dict[str, Any]
    ] = []

    def normalize_scope(
        value: Any,
    ) -> str:
        normalized = (
            str(value)
            .strip()
            .casefold()
        )

        if normalized in {
            "whole slide",
            "use whole slide",
            "full slide",
            "entire slide",
        }:
            return "Whole slide"

        if normalized in {
            "manual region",
            "select region",
            "selected region",
            "region",
        }:
            return "Manual region"

        raise AssertionError(
            "Unsupported target-scope value: "
            f"{value!r}"
        )

    def read_scope_radio() -> tuple[
        Any,
        list[Any],
    ]:
        radio = require_widget(
            app,
            "radio",
            "main_target_scope",
        )

        options = list(
            getattr(
                radio,
                "options",
                [],
            )
        )

        option_snapshots.append(
            [
                str(option)
                for option in options
            ]
        )

        if not options:
            raise AssertionError(
                "Target-scope radio has "
                "no display options."
            )

        return radio, options

    def resolve_set_value(
        radio: Any,
        display_options: list[Any],
        canonical_value: str,
    ) -> Any:
        # With format_func, AppTest.options contains formatted labels,
        # while set_value normally requires the underlying canonical
        # option value.
        formatter = getattr(
            radio,
            "format_func",
            None,
        )

        if callable(formatter):
            try:
                formatted = formatter(
                    canonical_value
                )
            except Exception:
                formatted = None

            if formatted in display_options:
                return canonical_value

        if canonical_value in display_options:
            return canonical_value

        expected_scope = normalize_scope(
            canonical_value
        )

        for option in display_options:
            try:
                option_scope = (
                    normalize_scope(
                        option
                    )
                )
            except AssertionError:
                continue

            if option_scope == expected_scope:
                return option

        raise AssertionError(
            "Unable to resolve radio value for "
            f"{canonical_value!r}. "
            "Display options: "
            f"{[str(item) for item in display_options]}"
        )

    def select_scope(
        canonical_value: str,
        step_name: str,
    ) -> None:
        radio, options = (
            read_scope_radio()
        )

        value_to_set = resolve_set_value(
            radio,
            options,
            canonical_value,
        )

        selection_records.append(
            {
                "requested_canonical": (
                    canonical_value
                ),
                "set_value": str(
                    value_to_set
                ),
                "display_options": [
                    str(option)
                    for option in options
                ],
            }
        )

        radio.set_value(
            value_to_set
        )

        run_step(
            app,
            completed,
            step_name,
        )

        session_value = (
            app.session_state[
                "main_target_scope"
            ]
        )

        actual_canonical = (
            normalize_scope(
                session_value
            )
        )

        if (
            actual_canonical
            != canonical_value
        ):
            raise AssertionError(
                "Target-scope selection did not "
                "produce the expected canonical "
                "session value. "
                f"requested={canonical_value!r}, "
                f"session={session_value!r}, "
                f"normalized={actual_canonical!r}"
            )

    select_scope(
        "Manual region",
        "select_manual_region",
    )

    # The browser-only drawing component is replaced with a
    # deterministic placeholder during AppTest. Repeated clear
    # operations still verify callback and rerun stability.
    for index in range(2):
        clear_button = require_widget(
            app,
            "button",
            "main_clear_region_button",
        )

        clear_button.click()

        run_step(
            app,
            completed,
            f"clear_region_{index}",
        )

        current_scope = normalize_scope(
            app.session_state[
                "main_target_scope"
            ]
        )

        if current_scope != "Manual region":
            raise AssertionError(
                "Clearing a region unexpectedly "
                "changed the target scope."
            )

    select_scope(
        "Whole slide",
        "select_whole_slide",
    )

    select_scope(
        "Manual region",
        "select_manual_region_again",
    )

    final_scope = normalize_scope(
        app.session_state[
            "main_target_scope"
        ]
    )

    if final_scope != "Manual region":
        raise AssertionError(
            "Unexpected final target scope: "
            f"{final_scope!r}"
        )

    return {
        "completed_steps": completed,
        "option_snapshots": (
            option_snapshots
        ),
        "selection_records": (
            selection_records
        ),
        "final_state": {
            "target_scope": (
                app.session_state[
                    "main_target_scope"
                ]
            ),
            "canonical_target_scope": (
                final_scope
            ),
            "manual_region_active": (
                session_state_value(app, "main_manual_region_active", False)
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
