# Live UI and Release Handoff

Status: not_started
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
