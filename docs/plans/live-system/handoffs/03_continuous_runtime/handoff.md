# Continuous Runtime Handoff

Status: not_started
Branch: `codex/live-system-integration-v1`
Scope: Checkpoints 4–5

## Purpose

对话 3 必须先读取 `../02_slide_sensing/handoff.md`，并在结束前用真实结果重写本文件。完整字段和证据要求见 `../../00_global_contract.md` 第 7 节。

## Required completion record

- Start/end commit 与 audio turn、orchestration checkpoint commits。
- normalized audio/VAD backend、turn thresholds、event/cancel/overrun semantics。
- controller public API、state transitions、thread ownership 与 busy policy。
- frozen turn/context types、sensing aggregation、confirmation resume/correction contract。
- deterministic E2E、failure recovery、multi-turn lifecycle 与 workspace evidence。

## Dependency on previous conversation

在对话 2 handoff 未完成前不得实现。audio/media timestamp 与 sensing snapshot clock 必须先有统一、可验证的解释，才能做 speech-window aggregation。
