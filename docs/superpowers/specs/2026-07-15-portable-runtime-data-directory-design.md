# Portable Runtime Data Directory Design

## Problem

The production Streamlit app defaults to an AutoDL-specific path under
`/root/autodl-tmp`. That path is invalid for the LenovoLinux user and makes a
normal launcher start fail unless `ATTENTIVE_RUNTIME_DATA_DIR` is set.

## Design

Keep `ATTENTIVE_RUNTIME_DATA_DIR` as the highest-priority explicit override.
When it is absent, resolve the runtime directory from the XDG user data home:

```text
${XDG_DATA_HOME:-~/.local/share}/attentive_slides
```

Use only `os.environ` and `pathlib.Path`; add no dependency or configuration
layer. Existing data is not moved or deleted.

## Verification

Update the existing Streamlit source-contract tests to require the environment
override, the XDG fallback, and the absence of the AutoDL path. Under the
project Lean Execution Profile, write the regression assertion before the
implementation but run only the focused GREEN test after both edits.

