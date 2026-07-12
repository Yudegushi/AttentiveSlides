# Foundation and Browser Media Handoff

Status: not_started
Branch: `codex/live-system-integration-v1`
Planned baseline: `705f1a2`
Scope: Checkpoints 0–1

## Purpose

对话 1 必须在结束前用真实结果重写本文件，交付 AutoDL preflight 与 browser media transport gate。完整字段和证据要求见 `../../00_global_contract.md` 第 7 节。

## Required completion record

- Start/end commit 与每个 checkpoint commit。
- AutoDL Python/CUDA/GPU/dependency 与 baseline test evidence。
- 选定 transport、fallback 决策、packet/queue API 与 cleanup 语义。
- 3-minute browser smoke、OFF/disconnect 结果；未执行项必须明确标记。
- 下一对话必须读取的 files、commits、tests、known risks 与 workspace state。

## Current workspace fact

规划对话已从 `feature/api-llm-pipeline@705f1a2` 创建共同分支；创建时工作树干净。执行对话仍须 fetch 并重新验证远端与工作树。
