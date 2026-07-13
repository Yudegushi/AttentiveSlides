# Live UI and Release Handoff

Status: partial - automated Checkpoints 6-7 complete; live tutor browser flow blocked at controlled PDF upload.
Branch: `codex/live-system-integration-v1`
Scope: Checkpoints 6–7

## Purpose

对话 4 必须先读取 `../03_continuous_runtime/handoff.md`，并在结束前用最终实测结果重写本文件。完整字段和证据要求见 `../../00_global_contract.md` 第 7 节。

## Required completion record

- Start/end commit、Checkpoint 6–7 commits 与最终 branch HEAD。
- live app/controller ownership、confirmation/correction 与 grounded tutor integration。
- automated/manual verification matrix、5-turn live evidence、启动与 SSH forwarding 命令。
- provider/model/dependency requirements、latency/transport observations与 error recovery。
- known limitations、not-run/blocked items、push 状态与 clean workspace evidence。

## Dependency on previous conversation

在对话 3 handoff 未完成且 controller lifecycle/E2E tests 不稳定时，不得用 Streamlit UI 掩盖 backend 缺口。现有 grounded API/XAI pipeline 必须复用，不能新建平行 DashScope client。

## Completion record

- Start HEAD: 4f19b6b; baseline: feature/api-llm-pipeline@705f1a2.
- Checkpoint 6: a01d8e7 feat: add live Streamlit interface.
- Checkpoint 7: af29b1a feat: connect live runtime to grounded tutor.
- This handoff and its release documentation are committed after final checks.
  No branch was pushed, merged, reset, cleaned, or switched.

## Interfaces and lifecycle choices

- apps/streamlit_live.py caches one LiveViewModel. The UI owns only commands
  and rendering; callbacks only convert, timestamp, and enqueue packets.
- SystemController retains idempotent lifecycle, a single active turn, frozen
  turn context, and confirmation resume. LiveTurnRunner still builds
  PipelineInputBundle and calls the canonical pipeline. Corrections replace
  predictions before the tutor call.
- LiveTutorAdapter defaults to deterministic TutorAgent. Optional grounded mode
  lazily reuses GroundedTutorAgent, OpenAICompatibleLLMClient, prompt, parser,
  validator, and fallback; it returns the compatible legacy response.
- LiveTelemetryLogger wraps InteractionLogger. JSONL keeps canonical fields and
  safe provider/model/latency/usage, resolved/confirmed AOI, context sources,
  validation, and fallback fields. No raw media, prompts, request IDs, secrets,
  raw provider responses, or hidden reasoning are logged.
- The view exposes safe state, packet stats, coarse gaze, transcript/timing,
  confirmation, response, sanitized XAI, and diagnostics. It never recreates
  workers on a Streamlit rerun.

## Automated evidence

All commands ran in
/root/autodl-tmp/workspace/AttentiveSlides-live-system with
/root/miniconda3/envs/attentive-app/bin/python because the SSH shell has no
python alias.

- C6 targeted: 30 tests passed; C6 RED -> GREEN focused: 11 tests; C6 full:
  222 tests passed.
- C7 RED -> GREEN focused suite: 25 tests; full
  python -m unittest discover -s tests -v: 227 tests passed.
- python -m compileall modules apps scripts tests passed.
- python scripts/demo_tutor_loop.py completed deterministic
  confirmation/correction scenarios and wrote its existing demo JSONL.
- Both evaluations passed: reference-resolution had all four metrics 1.0 over
  eight scenarios; scenario-output accuracy was 1.0.

Automated tests used fakes or synthetic packets only: no real camera/microphone
and no real LLM/API call.

## Manual browser acceptance

Attempted on 2026-07-13:

1. A loopback-only Streamlit live UI ran on AutoDL 8512 and opened at local
   http://localhost:8503 through ssh -N -L 8503:127.0.0.1:8512 AutoDL. The
   deterministic selection, master switch, transport/gaze/turn panels, AOI
   surface, confirmation area, and developer trace rendered.
2. A valid two-page temporary PDF was generated on AutoDL and copied locally.
   The controlled browser exposed its file input but could not inject the PDF;
   the UI stayed without a deck. Starting the live controller, speaking a
   deictic request, confirmation/correction, and inspecting a live JSONL line
   are **not verified**. No real provider was selected or called.
3. The single-origin fallback ran on remote 8513 through local 8504. With
   camera/microphone permission it reached 4.68 video FPS and 10.92 audio
   chunks/s, queue depths 3 and 63. After OFF and 1.2 seconds, both depths were
   zero and cleanup was stopped: browser stopped.
4. Fallback validates browser transport and stop cleanup only; it does not
   substitute for the blocked live tutor turn.

Local 8501 was already an unrelated SSH listener, so temporary 8503/8504 ports
were used without disturbing it. The temporary AutoDL services and SSH tunnels
started for acceptance were stopped afterwards.

## Interface difference, risk, and remaining manual gate

The existing AutoDL SSH TCP limitation can prevent Streamlit WebRTC from
playing even though same-origin fallback transports packets. Both paths remain
documented with distinct scope; no controller, packet, queue, snapshot-store,
or canonical pipeline contract was changed to work around it.

The incomplete live manual flow is a release risk. In an interactive browser
with file upload support, load a real PDF, enable the master switch, speak a
deictic request, select a correction, check data/logs/live_interactions.jsonl,
then stop or close the page.

## Final state

After the documentation commit: branch remains
codex/live-system-integration-v1; git diff --check is clean; no temporary
acceptance process remains; push status is **not pushed**.

## Chrome retry prerequisite

A second Chrome retry reached the standard file chooser for the generated
temporary PDF, but fileChooser.setFiles failed with `Not allowed`. Chrome
requires the ChatGPT Chrome Extension setting **Allow access to file URLs**
before controlled upload can continue. This is an external local permission,
not a live UI, media, controller, or pipeline failure. No code was changed.

After enabling it at chrome://extensions -> ChatGPT Chrome Extension ->
Details, rerun the complete live acceptance from PDF upload through five turns,
confirmation/correction, JSONL/XAI inspection, and OFF/disconnect cleanup.
