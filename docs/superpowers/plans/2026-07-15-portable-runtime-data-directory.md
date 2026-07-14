# Portable Runtime Data Directory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the AutoDL-only runtime default with a portable XDG user-data path while preserving the existing environment override.

**Architecture:** Keep path selection at the existing `RUNTIME_DATA_DIR` constant. Use `ATTENTIVE_RUNTIME_DATA_DIR` first; otherwise derive `attentive_slides` from `XDG_DATA_HOME` or `Path.home() / ".local" / "share"`.

**Tech Stack:** Python standard library (`os`, `pathlib`), `unittest`

## Global Constraints

- Do not add dependencies or a new configuration abstraction.
- Do not move or delete existing runtime data.
- Follow the project Lean Execution Profile: do not run RED; run one focused GREEN group.

---

### Task 1: Make the runtime default portable

**Files:**
- Modify: `apps/streamlit_attentive_slides.py:135`
- Test: `tests/test_streamlit_attentive_slides.py:122`

**Interfaces:**
- Consumes: `ATTENTIVE_RUNTIME_DATA_DIR`, optional `XDG_DATA_HOME`, and `Path.home()`.
- Produces: the existing `RUNTIME_DATA_DIR: Path` constant.

- [ ] **Step 1: Update the regression contract before production code**

```python
def test_runtime_data_dir_is_environment_configurable(self) -> None:
    self.assertIn('"ATTENTIVE_RUNTIME_DATA_DIR"', self.source)

def test_runtime_data_dir_defaults_to_xdg_user_data(self) -> None:
    self.assertIn('"XDG_DATA_HOME"', self.source)
    self.assertIn('Path.home() / ".local" / "share"', self.source)
    self.assertNotIn("/root/autodl-tmp", self.source)
```

- [ ] **Step 2: Replace the hard-coded default**

```python
RUNTIME_DATA_DIR = Path(
    os.environ.get(
        "ATTENTIVE_RUNTIME_DATA_DIR",
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        / "attentive_slides",
    )
)
```

- [ ] **Step 3: Run the focused GREEN test module**

Run:

```bash
/home/charles/miniconda3/envs/pyboe/bin/python -m unittest tests.test_streamlit_attentive_slides -v
```

Expected: all tests in `tests.test_streamlit_attentive_slides` pass with exit code 0.

- [ ] **Step 4: Commit the bounded fix**

```bash
git add apps/streamlit_attentive_slides.py tests/test_streamlit_attentive_slides.py \
  docs/superpowers/specs/2026-07-15-portable-runtime-data-directory-design.md \
  docs/superpowers/plans/2026-07-15-portable-runtime-data-directory.md
git commit -m "fix: use portable runtime data directory"
```
