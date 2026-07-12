# Slide and Sensing Handoff

Status: not_started
Branch: `codex/live-system-integration-v1`
Scope: Checkpoints 2–3

## Purpose

对话 2 必须先读取 `../01_foundation_media/handoff.md`，并在结束前用真实结果重写本文件。完整字段和证据要求见 `../../00_global_contract.md` 第 7 节。

## Required completion record

- Start/end commit 与 RealSlideProvider、human-sensing checkpoint commits。
- deck/slide/provider 构造方式、explicit deck ID、AOI selection policy 与 fixture coverage。
- canonical mapping、snapshot/window-query API、timestamp/freshness/slide-mismatch policy。
- worker ownership、inference cadence、stop/cleanup 与 live smoke evidence。
- 下一对话必须读取的 files、commits、tests、known risks 与 workspace state。

## Dependency on previous conversation

在对话 1 handoff 未完成前不得开始实现。若 transport packet contract 或 timestamp contract 未确定，本阶段必须先停在 preflight，不得自行建立不兼容的第二套 media source。
