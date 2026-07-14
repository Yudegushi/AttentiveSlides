# LLM AOI / Slide Size / Media Routing Execution Log

This ledger accompanies `docs/plans/UI-integration/2026-07-14-llm-aoi-slide-media-execution.md`. Update it only while executing that plan.

## Fixed Context

- Repository: `/root/autodl-tmp/workspace/AttentiveSlides-ui-live-integration`
- Branch: `codex/ui-live-runtime-integration-v1`
- Approved spec: `docs/superpowers/specs/2026-07-14-llm-aoi-slide-sizing-media-routing-design.md`
- Implementation plan: `docs/plans/UI-integration/2026-07-14-llm-aoi-slide-media-execution.md`
- No extra branch/worktree, no push without separate authorization.

## Checkpoint Ledger

| Checkpoint | Status | Focused verification | Commit | Notes / next action |
|---|---|---|---|---|
| 1. Media routing | Complete | 23/23 focused tests pass | `HEAD` (`fix: restore Streamlit media routing`) | Checkpoint 2 unblocked |
| 2. Slide width | Complete | 54/54 focused tests pass | `HEAD` (`feat: add adjustable slide width`) | Checkpoint 3 unblocked |
| 3. Current-page LLM AOI | Complete | 60/60 focused + 22/22 review-fix tests pass | `HEAD` (`fix: harden LLM AOI activation boundaries`) | Checkpoint 4 unblocked |
| 4. Deck batch/final acceptance | Code/focused complete | 32/32 focused tests pass | Pending | Final full suite and browser smoke pending |

## Verification Budget

- [x] Checkpoint 1 focused group run once after implementation
- [x] Checkpoint 2 focused group run once after implementation
- [x] Checkpoint 3 focused group run once after implementation
- [x] Checkpoint 4 focused group run once after implementation
- [ ] Final full suite run once after all checkpoints
- [ ] Final browser smoke session run once
- [ ] Real LLM calls did not exceed one text-heavy plus one visual-heavy page

## Current Resume Point

- Next unchecked step: `4.6`
- Last known blocker: none
- Uncommitted in-scope files: Checkpoint 4 code, tests, and this ledger pending commit
- Out-of-scope/user-owned changes observed: none recorded

## Execution Notes

Append concise dated entries in this form; never record secrets or full LLM responses:

```text
YYYY-MM-DD HH:MM CST — Checkpoint N / Step N.N
Changed: <exact files>
Verified: <exact command>; <pass/fail count>
Decision/blocker: <only if relevant>
Next: <next unchecked step>
```

2026-07-14 19:14 CST — Checkpoint 1 / Step 1.1
Changed: `docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md`
Verified: `git status --short --branch`; branch `codex/ui-live-runtime-integration-v1`, clean worktree, ahead by two approved documentation commits
Decision/blocker: `/media/*` is still selected and registered as ingress capture traffic, colliding with Streamlit media/download assets; no blocker
Next: Step 1.2

2026-07-14 19:16 CST — Checkpoint 1 / Steps 1.2–1.5
Changed: `tests/test_live_single_port_launcher.py`, `tests/test_single_port_transport.py`, `scripts/run_live_single_port.py`, `modules/media/single_port_transport.py`
Verified: `/root/miniconda3/envs/attentive-app/bin/python -m unittest tests.test_live_single_port_launcher tests.test_single_port_transport -v`; expected red 19 passed, 4 failed; green 23 passed, 0 failed
Decision/blocker: capture moved to `/attentive-media/*`; `/media/*` restored to ordinary Streamlit routing; no blocker
Next: Step 1.6

2026-07-14 19:17 CST — Checkpoint 1 / Step 1.6
Changed: `docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md`
Verified: `git diff --check`; clean; reviewed only the five in-scope diffs; no old `/media/*` capture route remains and `/capture` still selects ingress
Decision/blocker: checkpoint commit is identified symbolically as `HEAD` in this self-contained commit; record its resolved hash in the execution report; no blocker
Next: Step 2.1

2026-07-14 19:24 CST — Checkpoint 2 / Steps 2.1–2.6
Changed: `modules/system/main_ui_state.py`, `modules/ui/slide_viewport_component/__init__.py`, `modules/ui/slide_viewport_component/index.html`, `apps/streamlit_attentive_slides.py`, `tests/test_main_ui_state.py`, `tests/test_slide_geometry.py`, `tests/test_compact_main_layout.py`, `tests/test_streamlit_attentive_slides.py`
Verified: `/root/miniconda3/envs/attentive-app/bin/python -m unittest tests.test_main_ui_state tests.test_slide_geometry tests.test_compact_main_layout tests.test_streamlit_attentive_slides -v`; expected red 48 passed, 3 failed, 3 errors; green 54 passed, 0 failed
Decision/blocker: width is session-level rather than a turn default; iframe/root stay full width, only centered `#slide` scales; normalized manual bbox reset identity remains deck, slide, drawing mode, and explicit layout revision; no blocker
Next: Step 2.7

2026-07-14 19:25 CST — Checkpoint 2 / Step 2.7
Changed: `docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md`
Verified: `git diff --check`; clean; reviewed only the nine in-scope diffs; `report()` and drawing normalization still use `image.getBoundingClientRect()`, `display_width_percent` is absent from manual bbox reset identity, and turn reset does not own the width preference
Decision/blocker: checkpoint commit is identified symbolically as `HEAD` in this self-contained commit; record its resolved hash in the execution report; no blocker
Next: Step 3.1

2026-07-14 20:15 CST — Checkpoint 3 / Steps 3.1–3.9
Changed: `modules/slide/llm_aoi.py`, `modules/slide/slide_parser.py`, `modules/slide/ocr.py`, `modules/slide/aoi_manager.py`, `scripts/pdf_native_worker.py`, `modules/system/uploaded_deck_service.py`, `modules/system/real_slide_provider.py`, `modules/system/main_ui_state.py`, `apps/streamlit_attentive_slides.py`, and the seven focused test modules
Verified: focused group expected red ran 52 tests with 2 failures and 7 errors for missing Checkpoint 3 contracts; focused green ran 60 tests with 0 failures/errors; all generator/worker boundaries were fake-only and no network call was made
Decision/blocker: LLM variants remain in separate `llm_*` fields; deterministic `aois`, RLock/atomic replacement, `children`, `allow_ocr=False`, DPI-specific images, and rule/auto fallback remain intact; no blocker
Next: Step 3.10

2026-07-14 20:16 CST — Checkpoint 3 / Step 3.10
Changed: `docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md`
Verified: security/state diff review and commit recorded in the Checkpoint 3 execution report
Decision/blocker: no secret, header, endpoint, or full model response is persisted or shown; built-in decks and thumbnail/navigation paths never prepare LLM AOIs; no blocker
Next: Step 4.1

2026-07-14 20:35 CST — Checkpoint 3 / review hardening
Changed: `modules/slide/aoi_manager.py`, `modules/system/real_slide_provider.py`, `modules/system/uploaded_deck_service.py`, `tests/test_llm_aoi.py`, `tests/test_real_slide_provider.py`, `tests/test_uploaded_deck_service.py`
Verified: targeted expected red ran 22 tests with exactly 3 failures; targeted green ran 22 tests with 0 failures/errors; no browser, full suite, or network call
Decision/blocker: provider activation now reuses complete manager eligibility; worker exceptions cross the workspace boundary only as a fixed non-sensitive message; model anchors are projected to flat stable fields without `children`; no blocker
Next: Step 4.1

2026-07-14 20:40 CST — Checkpoint 4 / Steps 4.1–4.5
Changed: `modules/slide/aoi_manager.py`, `modules/system/uploaded_deck_service.py`, `apps/streamlit_attentive_slides.py`, `tests/test_uploaded_deck_service.py`, `tests/test_main_ui_widget_inventory.py`, `tests/test_streamlit_attentive_slides.py`, `docs/plans/UI-integration/handoffs/llm-aoi-slide-media-log.md`
Verified: `/root/miniconda3/envs/attentive-app/bin/python -m unittest tests.test_uploaded_deck_service tests.test_main_ui_widget_inventory tests.test_streamlit_attentive_slides -v`; expected red ran 32 tests with 25 passed, 1 failure, and 6 errors, all for missing Checkpoint 4 contracts; focused green ran 32 tests with 0 failures/errors in 0.987s
Decision/blocker: batch processing is ascending and synchronous, skips profile-eligible pages, continues with fixed non-sensitive `fallback_used` results after per-page exceptions, invokes the callback once per completed page without swallowing callback exceptions, and persists the exact UI summary across one rerun; no real LLM, full suite, or browser smoke was run
Next: Step 4.6 final full suite, then Step 4.7 browser smoke (both pending controller review)
