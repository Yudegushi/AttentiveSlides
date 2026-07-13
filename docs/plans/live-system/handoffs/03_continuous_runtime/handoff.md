# Continuous Runtime Handoff

Status: in_progress
Branch: `codex/live-system-integration-v1`
Scope: Checkpoints 4–5
Start commit: 9ccd5f3 (docs: finalize slide sensing handoff)

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

## Pre-implementation decisions and deviations

- BrowserMediaSource audio packets expose source-relative timestamps
  (`media_time_seconds` or `browser_performance_seconds`), while
  SensingSnapshotStore windows use server-monotonic `processed_at`. AudioWorker
  will explicitly anchor each contiguous source clock to the worker monotonic
  clock at dequeue time, then VoiceTurnDetector will emit only that normalized
  timeline. Context aggregation will not compare raw browser timestamps.
- AutoDL does not have `webrtcvad` installed. The implementation uses an
  injectable WebRTC-compatible protocol and optional WebRTC adapter, with a
  deterministic local energy fallback. Unit tests inject deterministic VADs and
  never download a model or open a microphone.
- BrowserMediaSource's immutable AudioPacket and bounded queue interface is
  unchanged. AudioWorker consumes the queue outside callbacks; raw PCM is kept
  only in bounded pre-roll/maximum-turn memory and a temporary WAV is deleted
  immediately after transcription.
