# 对话 4：Checkpoint 6–7 — Live UI and Release

> 目标：只在 backend 已稳定后暴露产品 UI，接入现有 grounded API tutor/XAI 能力，并完成 AutoDL 可复现实测、文档与发布准备。

## 1. 开始前读取

按 `00_global_contract.md` 第 4 节执行，必须先读：

- `handoffs/03_continuous_runtime/handoff.md`
- handoff 指定的 controller/state/turn commits 与 tests
- `apps/streamlit_demo.py`
- `apps/streamlit_grounded_xai.py`
- `modules/system/demo_view_model.py`
- `modules/system/xai_view_model.py`
- `modules/tutor/api_llm_client.py`
- `modules/tutor/grounded_tutor_agent.py`
- `modules/tutor/tutor_request_adapter.py`
- `modules/tutor/grounded_prompt.py`
- `modules/tutor/response_parser.py`
- `modules/tutor/grounding_validator.py`
- `modules/tutor/template_fallback.py`
- `docs/streamlit_xai.md`
- commits `ef6a1e7..705f1a2`

先确认 grounded tutor 的实际 construction/response contract，不能按旧 master plan 新建平行 `dashscope_llm.py`。

## 2. Checkpoint 6 — Live Streamlit UI

### 产品边界

保留 `apps/streamlit_demo.py` 和 `apps/streamlit_grounded_xai.py` 作为 regression/reference app，新增：

```text
apps/streamlit_live.py
modules/system/live_view_model.py
tests/test_live_view_model.py
docs/live_ui_usage.md
```

核心 inference、thread、VAD、STT、turn aggregation 与 tutor orchestration 不得进入 UI 文件。Streamlit rerun 只能读取 view model、发送 controller command，并通过 resource/session ownership 复用同一 controller。

### UI 必须包含

- PDF upload 与 deck load state。
- slide navigation、slide image、AOI overlay。
- master switch。
- media permission/connection 与 transport state。
- runtime state 与 busy/error status。
- camera preview，且与 derived gaze signals 明确区分。
- latest gaze grid、predicted AOI、confidence 与 freshness。
- transcript 与 turn timing。
- confirmation candidates/correction。
- tutor response 与 grounded/XAI evidence。
- latency/error summary。
- optional developer panel，用于 queue/drop/thread/transport trace。

### 交互与 lifecycle

- ON：start controller/media once；OFF：stop all workers。
- high-confidence turn 显示 grounded response。
- uncertain turn 先显示 candidates，用户确认/纠正后才生成 final answer。
- manual transcript 与 file audio 保留为明确 debug/regression fallback，不作为 live acceptance 替代品。
- rerun、refresh、deck reload、slide change 与 exception 不创建 duplicate worker/model。
- derived learning signals 使用谨慎语言，不展示未经验证的 cognition/emotion claim。

### Automated acceptance

- view-model state mapping 不启动 Streamlit server。
- ON/OFF command idempotency。
- confirmation/correction action routing。
- rerun ownership 与 no-duplicate-worker contract。
- disconnect/error/degraded state copy。
- existing demo/XAI tests 不回归。
- 全量 regression tests 与 `git diff --check`。

### Manual acceptance

通过 SSH forwarding：上传 PDF、ON、camera/mic、看向 AOI 并说 “explain this”、自动 speech-end/STT、target/confirmation、grounded response、OFF cleanup；连续至少 5 turns，无需重启 app。

完成后独立 commit，建议 `feat: add live Streamlit interface`。

## 3. Checkpoint 7 — Grounded real LLM, evaluation and documentation

### 复用现有 LLM pipeline

当前已有 `OpenAICompatibleLLMClient.from_env()` 与 `GroundedTutorAgent`。本 checkpoint 负责：

1. 为 `TutorTurnRunner`/live app 提供 explicit tutor selection：默认 deterministic mock/template path；用户启用且环境已配置时使用 grounded API path。
2. 复用现有 request adapter、structured prompt、parser、grounding validator、retry/fallback 与 XAI view model；不复制 prompt 或 validation。
3. API key 只从 environment/Streamlit secrets 读取；不写入 repo、UI、log 或 handoff。
4. provider failure 产生可恢复 UI error/fallback，并让 controller 回到正确 state。
5. 记录 provider/model、latency、usage、resolved AOI/context IDs、validation/fallback 状态；不记录 raw chain-of-thought 或完整敏感 payload。
6. tests 使用 fake client/MockLLM，不访问真实 API。

若现有 `GroundedTutorAgent` 与 canonical `TutorAgent` protocol 不完全兼容，应在 live runner 边界增加 adapter；不要修改 canonical interaction pipeline 去理解 provider-specific response。

### Evaluation

Mandatory：

```bash
python -m compileall modules apps scripts tests
python -m unittest discover -s tests -v
python scripts/demo_tutor_loop.py
python evaluation/eval_reference_resolution.py
python evaluation/eval_scenario_outputs.py
git diff --check
```

Manual：

- browser media 3-minute smoke。
- 5-turn live interaction。
- high confidence / confirmation / correction / no-gaze。
- optional DashScope turn（只有 key 可用时）。
- JSONL/XAI log inspection。
- OFF/restart、disconnect 与 provider/STT error recovery。

必须区分 mandatory automated PASS、manual PASS、not run 与 blocked。不得声称未测量的 gaze/VAD accuracy 或 learning effectiveness。

### 文档收口

更新：

```text
PROJECT_PROGRESS.md
README.md
docs/member1_member2_integration.md
docs/browser_media_runtime.md
docs/continuous_interaction_design.md
docs/live_ui_usage.md
```

所有运行说明以 AutoDL 与 `ssh -N -L 8501:127.0.0.1:8501 AutoDL` 为准。旧 LenovoLinux 结果可作为历史证据保留，但不能继续写成 primary runtime。

建议把 UI 与 grounded API integration 分开 commit：

```text
feat: connect live runtime to grounded tutor pipeline
docs: finalize live system integration guide
```

## 4. 最终 handoff 与 branch 状态

结束前更新：

`docs/plans/live-system/handoffs/04_live_release/handoff.md`

最终 handoff 必须记录：

- 所有 Checkpoint 6–7 commits 与最终 branch HEAD。
- 自动与人工 verification matrix。
- 实际启动/SSH forwarding 命令。
- dependency/model/env requirements，但不含 secrets。
- transport、sensing FPS、VAD/STT 与 LLM latency 的实测范围。
- known limitations 与未验证项。
- 是否 push；不要自动 merge `main`。
- `git status --short --branch` 与任何本地运行进程/临时数据。

只有 `00_global_contract.md` 第 8 节和完整 master plan 的完成定义全部满足，才可把阶段标记为 complete。
