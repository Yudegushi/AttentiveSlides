# AttentiveSlides Live System：全局执行契约

> 本文件是四个 Codex 对话的共同入口。完整、未经删减的阶段规划保存在
> `docs/plans/attentive_slides_live_system_integration_plan.md`。分卷文档只负责把该规划变成可顺序交接的工作包；若两者冲突，以本文件记录的“基线校正”和完整 master plan 的系统约束共同裁决。

## 1. 已确认的云端基线

- SSH config host：`AutoDL`
- 仓库：`/root/autodl-tmp/workspace/AttentiveSlides`
- 共同开发分支：`codex/live-system-integration-v1`
- 分支起点：`feature/api-llm-pipeline@705f1a2`
- `integration-v100@353c033` 是该起点的祖先，落后 8 个提交。
- 创建分支时工作树干净，GitHub 上 `feature/api-llm-pipeline`、`integration-v100`、`main` 与云端对应 remote-tracking ref 一致。

选择最新 feature 分支是有意决定：它已经包含 `integration-v100` 的 Member 1 slide/AOI 与 Member 2 human-sensing 导入，同时补充了结构化 grounded LLM、DashScope-compatible client、grounding validation、evaluation 和 XAI UI。后续不得为了遵循旧文字而退回 `integration-v100`。

## 2. Master plan 基线校正

完整 master plan 中 Checkpoint 7 建议新增 `modules/tutor/dashscope_llm.py`，这项建议已被最新代码取代。当前已有：

- `modules/tutor/api_llm_client.py::OpenAICompatibleLLMClient`
- `modules/tutor/grounded_tutor_agent.py::GroundedTutorAgent`
- structured request/response schemas、prompt builder、parser、grounding validator 与 template fallback
- `apps/streamlit_grounded_xai.py` 与 `modules/system/xai_view_model.py`

因此 Checkpoint 7 的正确任务是把 live runtime 接入并复用上述能力，补齐 lifecycle、view-model、logging 和 live evaluation；不得平行再造第二套 DashScope client、prompt pipeline 或 grounding gate。

`PROJECT_PROGRESS.md` 仍描述旧的 `LenovoLinux_Dorm` 执行环境，这是待更新文档，不是本阶段的实际执行基线。当前阶段统一以 AutoDL 为准。

## 3. 四个对话的唯一顺序

| 对话 | Checkpoints | 分卷 | 必须写入的 handoff |
|---|---:|---|---|
| 1 | 0–1 | `01_foundation_media.md` | `handoffs/01_foundation_media/handoff.md` |
| 2 | 2–3 | `02_slide_sensing.md` | `handoffs/02_slide_sensing/handoff.md` |
| 3 | 4–5 | `03_continuous_runtime.md` | `handoffs/03_continuous_runtime/handoff.md` |
| 4 | 6–7 | `04_live_release.md` | `handoffs/04_live_release/handoff.md` |

四个对话必须在同一分支上顺序完成。后一个对话从前一个对话已经提交并验证的 HEAD 继续，不创建平行实现分支，不 cherry-pick 同阶段的替代实现。

## 4. 每个对话开始时的强制读取顺序

每个对话在改代码前必须完成以下步骤并在自己的 handoff 中留下证据：

1. 连接 `AutoDL`，进入 `/root/autodl-tmp/workspace/AttentiveSlides`。
2. 运行 `git status --short --branch`，确认分支为 `codex/live-system-integration-v1` 且不会覆盖未提交工作。
3. 阅读完整 master plan、本文件和当前分卷。
4. 阅读上一对话的 handoff；对话 1 没有本阶段 handoff，应改读 `PROJECT_PROGRESS.md`、`docs/integration_sources.md`、`docs/member1_member2_source.md`、`docs/audio_merge_readiness.md` 和 `docs/streamlit_xai.md`。
5. 运行 `git log --oneline --decorate -n 20`，再阅读上一 handoff 记录的 commit：至少执行 `git show --stat <sha>`；涉及接口时执行 `git show <sha> -- <relevant-path>`。
6. 阅读当前分卷列出的相关代码与测试，验证文档里的接口仍存在；不得只凭规划文件直接实现。
7. 运行当前分卷规定的 baseline/targeted tests，记录初始失败与 dependency gap。
8. 若远端结构、dependency 或接口与规划明显不一致，先更新当前分卷中的“发现与偏差”，再调整实现；不得静默偏离 canonical contract。

## 5. 全局系统边界

### 5.1 Canonical contract

- `modules/common/schemas.py` 继续是 system-level canonical schema。
- Member 1/2 dataclass 只能由 adapter 转换，不能扩散到 `modules/system/pipeline.py`、`modules/interaction/`、`modules/tutor/` 或 UI view model。
- schema 新字段必须有默认值、backward-compatible，并保持 mock/audio/grounded LLM tests 可运行。
- `ProviderBackedDeckStore` 当前在 deck ID 未知时会读取固定 slide 5；Checkpoint 2 必须消除这一行为，不能把它带入 live path。

### 5.2 Browser media contract

- 正式 cloud path 不使用 `cv2.VideoCapture(0)` 访问用户设备。
- 浏览器提供 webcam 与 microphone；AutoDL 处理 slide、sensing、VAD/STT、reference resolution、tutor 与 logging。
- media callback 只转换格式、附 timestamp、非阻塞写入 bounded queue、丢弃过旧数据；禁止在 callback 中运行 MediaPipe、Whisper、LLM 或调用 `st.*`。
- 默认不持久化 raw audio/video。
- Checkpoint 1 是真实 transport gate：WebRTC 失败必须进入同端口 fallback，不能退化成手动 upload 后宣称 live 完成。

### 5.3 Runtime contract

```text
STOPPED
→ STARTING
→ MONITORING
→ SPEECH_ACTIVE
→ FINALIZING_AUDIO
→ PROCESSING_TURN
→ WAITING_CONFIRMATION (only when required)
→ MONITORING
```

任何状态可进入 `ERROR → STOPPED`。`start()`/`stop()` 必须幂等；同一 session 只允许一个 active speech turn；所有 queue 必须有上限；stale frame/snapshot 必须显式降级；master switch OFF、browser disconnect 和页面退出必须清理 worker。

### 5.4 Human-centered contract

- gaze 只表述为 coarse AOI evidence，不声称 pixel-level eye tracking。
- learning state 只展示 observable signals，不声称真实 emotion、confusion、fatigue 或 cognition。
- uncertainty confirmation gate 不得被 live runtime 或 real LLM 绕过。
- user correction 永远覆盖 predicted target。
- raw chain-of-thought、API key、完整 provider payload 与隐私媒体不得进入 UI 或日志。

## 6. Checkpoint、测试与提交规则

- 每个 checkpoint 都要先跑 targeted tests，再跑全量 regression tests。
- 每个 checkpoint 独立 commit；不要把两个 checkpoint 压成一个巨大提交。
- 只提交与当前 checkpoint 有关的文件；发现已有用户改动时必须保留。
- 不直接修改或 merge `main`；不使用 `git reset --hard`、`git clean -fd` 或破坏性 checkout。
- 不自动升级 torch/CUDA build。
- 每次提交后运行 `git diff --check`；对话结束前确认 `git status --short --branch`。
- 在 handoff 中记录实际运行命令及结果，不能只写“tests pass”。

推荐提交边界：

```text
chore: audit AutoDL integration baseline
feat: add browser media transport
feat: add real slide provider
feat: adapt live human sensing outputs
feat: add continuous speech turn detection
feat: orchestrate live tutor turns
feat: add live Streamlit interface
feat: connect live runtime to grounded tutor pipeline
docs: finalize live system integration guide
```

## 7. Handoff 文件契约

各对话开始时，自己的 handoff 文件处于 `not_started`；结束前必须在同一提交序列中更新为真实结果。handoff 至少包含：

```markdown
# <Stage> Handoff

Status: complete | partial | blocked
Branch: codex/live-system-integration-v1
Start commit: <sha>
End commit: <sha>

## Delivered
按 checkpoint 列出已实现文件、关键接口和行为。

## Decisions and deviations
记录 transport/backend/policy 决策，以及相对 master plan 的任何偏差与原因。

## Verification evidence
逐条记录命令、PASS/FAIL、关键输出和人工 smoke 结果。

## Known issues and risks
记录仍会影响下一对话的 dependency、环境、性能、lifecycle 或 schema 风险。

## Next conversation must read
列出下一对话必须查看的 commit、文件和测试。

## Workspace state
记录 git status、未跟踪文件、运行中的进程、临时数据和是否已 push。
```

不得用 handoff 掩盖未完成 acceptance。未通过的测试、未执行的 manual gate 和 fallback 路径必须明确写为未验证。

## 8. 本阶段完成定义

只有完整 master plan 第 7 节的条件全部满足，且四份 handoff 都有可追溯验证证据，阶段才算完成。最后一个对话负责把 `PROJECT_PROGRESS.md`、`README.md` 与 live runtime 文档更新为 AutoDL 的真实状态，并报告最终 branch HEAD；不要自动 merge 到 `main`。
