# AttentiveSlides UI + Live Multimodal Runtime 融合规划

> **目标**：以 `feature/api-llm-pipeline` 的新 UI 与最终 LLM workflow 为产品主体，接入 `codex/live-system-integration-v1` 的 browser audio/video、VAD/STT、gaze sensing 与 continuous runtime。  
> **阶段限制**：本阶段保留九宫格 gaze，不实现连续 gaze point；但固定可扩展接口，后续只替换 gaze resolver，不重构 UI、confirmation 或 LLM pipeline。
> **交付物**：远端分支 `codex/ui-live-runtime-integration-v1`。该分支是融合后的新开发基线；两个源分支与 `main` 保持不变。

---

## 1. 已确认的产品设计

### 正式入口

唯一正式用户入口：

```text
apps/streamlit_attentive_slides.py
```

`apps/streamlit_live.py` 保留为 diagnostic / regression app，不再作为最终产品 UI。

### 两种交互模式

```text
Manual mode
用户手动画框或选择 AOI
→ 输入文字
→ confirmation
→ LLM

Live mode
browser camera + microphone
→ gaze grid + STT
→ 自动生成 target / intent proposal
→ 按 confirmation policy 自动确认或等待用户确认
→ LLM
```

两种模式共用：

- PDF / Slides；
- AOI；
- `InteractionInput`；
- confirmation / correction；
- `main_tutor_integration`；
- `GroundedTutorAgent`；
- conversation history；
- XAI；
- final response UI。

### Confirmation policy

Sidebar 提供一个统一设置：

```text
Always confirm
Confidence-based auto
```

默认：

```text
policy = Always confirm
auto_confirm_threshold = 0.80
```

`Confidence-based auto` 仅使用 **AOI target confidence**。现阶段 STT confidence 不参与判断，但 `IntentInput.source_confidence` 保留为未来接口，当前写入 `None`。

### LLM 规则

正式 LLM 路径唯一为：

```text
main_tutor_integration
→ GroundedTutorAgent
→ OpenAICompatibleLLMClient
```

`LiveTutorAdapter` 不作为第二套 production LLM path。

API 失败时：

- UI 显示真实 API error；
- 保留当前 confirmed interaction，允许重试；
- 不返回 deterministic fallback answer；
- automated tests 仍使用 fake agent，不调用真实 API。

---

## 2. 当前分支与融合策略

当前已核查：

```text
feature/api-llm-pipeline
HEAD: 3af3c52
作用：新 UI、PDF workspace、interaction contract、confirmation、
conversation history、XAI、最终 grounded LLM

codex/live-system-integration-v1
HEAD: e3f1939
作用：单端口 browser media、audio/VAD/STT、gaze sensing、
continuous runtime、controller、live logging
```

两个分支从 `705f1a2` 分叉，已经 diverged。

### 工作分支

使用独立 worktree，从产品主体分支的已核查 SHA 创建：

```bash
git fetch origin feature/api-llm-pipeline codex/live-system-integration-v1
git worktree add \
  -b codex/ui-live-runtime-integration-v1 \
  /root/autodl-tmp/workspace/AttentiveSlides-ui-live-integration \
  3af3c527b1de4b7cf3abe9d72c32eac6f0a39745
cd /root/autodl-tmp/workspace/AttentiveSlides-ui-live-integration
git merge --no-ff e3f193928a2601422d5face51572eeca6ee08cb1
```

不得修改或 merge `main`。每个 checkpoint 完成后 commit 并 push 当前工作分支，但不得创建或合并 PR，除非用户另行授权。

### 冲突处理原则

当前 merge dry-run 只有一个文本冲突：

```text
modules/slide/aoi_manager.py
```

`slide_parser.py`、requirements 与 progress / usage documentation 仍需做语义检查，但当前不是文本冲突。

`aoi_manager.py` 的合并结果必须同时保留：

- 同学分支的 `allow_ocr`、native PDF worker 与 uploaded workspace 行为；
- live 分支的 `RLock`、atomic manifest save 与 concurrency safety。

---

## 3. 模块所有权

### 使用同学分支作为 canonical implementation

```text
apps/streamlit_attentive_slides.py
modules/common/interaction_contracts.py
modules/system/uploaded_deck_service.py
modules/system/main_ui_state.py
modules/system/manual_targeting.py
modules/system/manual_confirmation.py
modules/system/manual_intent.py
modules/system/main_tutor_integration.py
modules/system/conversation_history.py
modules/system/integrated_pipeline_xai.py
```

对应职责：

- UI 与视觉结构；
- PDF upload、slide thumbnail、navigation；
- manual target；
- confirmation / correction；
- unified `InteractionInput`；
- conversation history 与 XAI；
- final LLM invocation。

### 使用 live-system 分支作为 canonical implementation

```text
modules/media/*
modules/audio/audio_ring_buffer.py
modules/audio/streaming_vad.py
modules/audio/voice_turn_detector.py
modules/system/audio_worker.py
modules/system/sensing_worker.py
modules/system/sensing_snapshot_store.py
modules/system/controller.py
modules/system/turn_context.py
scripts/run_live_single_port.py
```

对应职责：

- browser camera / microphone；
- same-origin single-port HTTP transport；
- bounded media queues；
- VAD、speech turn、Whisper STT；
- face / gaze / learning-state sensing；
- lifecycle、cleanup、single active turn。

### 最小 integration layer

```text
ActiveDeckSlideProvider
SlideViewportComponent
LiveUIBridge
```

`LiveUIBridge` 在一个小模块内包含 proposal、容量为 1 的 thread-safe inbox、九宫格 AOI matching 与 runtime wiring。除非文件在实现时明显不可维护，不再为这些职责各建一层抽象。

这些模块只负责连接两套已验证实现，不得重写 PDF、media、confirmation 或 LLM。不得为未来 continuous gaze 预建 calibration framework、point resolver hierarchy 或通用 event bus。

---

## 4. 最终架构

```text
                    apps/streamlit_attentive_slides.py
                                │
             ┌──────────────────┴──────────────────┐
             │                                     │
       Manual mode                            Live mode
             │                                     │
manual target / typed text        browser camera + microphone
             │                         │             │
             │                    gaze grid      VAD + STT
             │                         │             │
             │                 viewport AOI          │
             │                    resolver           │
             │                         └──────┬──────┘
             │                                │
             └──────────────→ InteractionInput proposal
                                              │
                               confirmation policy
                              ┌───────────────┴──────────────┐
                              │                              │
                       Always confirm              Confidence-based auto
                              │                              │
                    confirm / correction          confidence >= threshold
                              └───────────────┬──────────────┘
                                              │
                                  main_tutor_integration
                                              │
                                    GroundedTutorAgent
                                              │
                                answer + history + XAI + log
```

---

## 5. 新增接口

### 5.1 ActiveDeckSlideProvider

UI 的 `UploadedDeckWorkspace` / `UploadedDeckBrowser` 是唯一 production deck source。

新增 adapter 实现现有 `SlideProvider`：

```python
class ActiveDeckSlideProvider:
    def set_browser(self, browser) -> None: ...
    def clear(self) -> None: ...
    def get_slide_frame(self, slide_id: int) -> SlideFrame: ...
```

要求：

- 同一 deck、slide、AOI IDs 同时供 UI、sensing 和 tutor 使用；
- production runtime 不再单独加载第二份 `RealSlideProvider`；
- `RealSlideProvider` 仅保留测试或 diagnostic 用途；
- deck / slide change 清除旧 sensing snapshots 和 pending proposal。

### 5.2 SlideViewportGeometry

坐标统一使用 browser viewport CSS pixels：

```python
@dataclass(frozen=True)
class SlideViewportGeometry:
    deck_id: str
    slide_id: int
    layout_revision: int
    received_at: float
    viewport_width: float
    viewport_height: float
    device_pixel_ratio: float
    slide_rect: ViewportBBox
    aoi_rects: dict[str, ViewportBBox]
```

其中：

- canonical AOI 仍保存 normalized slide bbox；
- `ViewportBBox` 是独立的 CSS-pixel dataclass，不复用 normalized `AOI.bbox`；
- viewport bbox 只用于实时 gaze matching；
- `devicePixelRatio` 只记录，不将 CSS pixel 误称为物理屏幕 pixel；
- geometry 与 deck、slide、layout revision 绑定；
- `received_at` 在 Python 收到 component value 时使用 `time.monotonic()` 写入，不比较 browser clock 与 server clock；
- 本阶段不增加 geometry heartbeat。缺失 geometry，或 deck / slide / revision 不匹配即视为 stale，并禁止 auto-confirm。

### 5.3 当前 gaze 数据

本阶段直接复用现有 `GazePrediction` 的：

```text
slide_id
gaze_grid
confidence
stable_duration_sec
```

不新增只服务于九宫格的 `GazeObservation`。后续 continuous gaze 到来时再增加 point 字段与 resolver，不要求当前代码提前承担未知接口。

### 5.4 九宫格 target resolver

```python
def resolve_grid_target(
    proposal: LiveInteractionProposal,
    geometry: SlideViewportGeometry,
    aois: Sequence[AOI],
) -> LiveInteractionProposal: ...
```

阶段一规则：

1. 将 browser viewport 分成 3×3 cells；
2. 选择 `gaze_grid` 对应 cell；
3. 与 AOI viewport bbox 计算 overlap 和 center proximity；
4. 排除 `whole_slide`、footer 和不可学习 AOI；
5. 输出 predicted AOI、confidence、top-k alternatives；
6. 没有可靠候选时输出 `predicted_aoi_id=None`；
7. deterministic tie-breaking；
8. geometry stale、slide mismatch 或 revision mismatch 时禁止有效预测。

复用现有算法的最小评分形式：

```text
spatial_score = 0.7 * overlap_ratio + 0.3 * center_proximity
target_confidence = gaze.confidence * spatial_score
```

候选按 `(-score, aoi_id)` 排序；最高 `target_confidence < 0.35` 时 `predicted_aoi_id=None`。用户主动选择 `Confidence-based auto` 后，仍必须达到 UI threshold（默认 `0.80`）才自动调用 LLM。

production target 不再直接使用旧的“九宫格对 slide-normalized AOI”映射。旧映射可保留作 regression，但不得成为最终 UI 的 canonical target。

### 5.5 Live proposal 与 inbox

background worker 不直接修改 `st.session_state`。

```python
@dataclass(frozen=True)
class LiveInteractionProposal:
    interaction_id: str
    deck_id: str
    slide_id: int
    layout_revision: int
    transcript: str
    gaze_grid: str
    gaze_confidence: float
    stable_duration_sec: float
    predicted_aoi_id: str | None
    target_confidence: float
    alternatives: tuple[TargetCandidate, ...]
    original_speech_transcript: str

class LatestProposalInbox:
    def publish(self, proposal: LiveInteractionProposal) -> None: ...
    def pop(self) -> LiveInteractionProposal | None: ...
    def clear(self) -> None: ...
```

要求：

- 使用标准库 `queue.Queue(maxsize=1)`，新 proposal 覆盖未消费的旧 proposal；
- thread-safe；
- proposal 有唯一 interaction ID；
- Streamlit periodic fragment 消费 proposal；
- 同一 proposal 不得重复触发 API。

### 5.6 Live ingress 必要修复

融合后先修复两个已确认的 lifecycle 缺口：

1. `FallbackMediaIngress.reset_active_readiness(reason)` 清除 active session 的 video/audio receive times 并重新激活共享 source。外部 deck reload 停止 source 后，runtime 必须等待新的 video 和 audio 才能再次启动；旧 packet freshness 不得复用。
2. `LiveIngressService` 记录 coordinator 最后异常并从 task 状态生成 health。`/health` 在 coordinator 正常时返回 200，在 task done / exception 时返回 503，使 single-port launcher 能检测 lifecycle service 失效。

本阶段不增加独立 watchdog service、持久化健康历史或额外监控框架。coordinator 与 HTTP server 共用 event loop；event loop 阻塞时 health 请求本身会超时，因此不再维护 `coordinator_last_reconcile_at` stale policy。

---

# 6. Checkpoints

## Checkpoint 0 — Safe Merge and Canonical Ownership

### Context

两个分支已有各自完整 UI/runtime，但目前存在两套 app、两套 deck provider 和两套 tutor entry。

### Request

1. 创建 integration branch / worktree；
2. merge 两个分支并解决文本冲突；
3. 保留两个分支已有 tests；
4. 修复 deck reload media freshness；
5. 修复 coordinator health；
6. 明确 production ownership；
7. 建立 `ActiveDeckSlideProvider`；
8. 让 UI 与 live runtime 使用同一 deck、slide 和 AOI source。

### Output

- merge commit；
- canonical ownership document；
- `ActiveDeckSlideProvider`；
- combined requirements；
- ingress lifecycle regression tests；
- baseline regression report。

### Constraints

- 正式入口只能是 `streamlit_attentive_slides.py`；
- 不删除 diagnostic apps；
- 不调用真实 camera、microphone 或 API 跑 automated tests；
- 不在此 checkpoint 改写 UI 或 gaze algorithm。

### Acceptance

- 两个分支的原有 targeted tests 通过；
- uploaded PDF 只生成一份 canonical deck/manifest；
- UI 与 sensing 获得相同 AOI IDs；
- `aoi_manager.py` 同时保留 worker compatibility 和 lock/atomic save；
- deck reload 后必须收到新 video + audio 才能重启 runtime；
- coordinator 失败时 `/health` 返回 503；
- working branch push 成功，main 未变化。

---

## Checkpoint 1 — Slide Component and Viewport AOI Geometry

### Context

当前 UI 的 AOI bbox 是 slide-normalized；当前 gaze 是 browser/screen 九宫格。二者不能直接比较。

### Request

将主页面现有 slide workspace 替换为一个最小 custom Streamlit component，承担：

```text
slide image display
AOI overlay
manual rectangle selection
viewport geometry reporting
```

保留：

- 当前 slide 所占位置和空间；
- thumbnail strip；
- navigation；
- target / intent / answer 区域；
- 当前配色、边框和信息密度。

组件通过 `ResizeObserver`、scroll/resize listener 和 `getBoundingClientRect()` 报告：

- viewport size；
- slide content rect；
- AOI viewport rects；
- layout revision；
- manual rectangle。

### Technical gate

先做最小 spike，确认在正式 single-port launcher 下：

1. component 能返回 browser viewport CSS coordinates；
2. iframe / component frame offset 能正确计入；
3. sidebar、resize、scroll 后 rect 更新；
4. PDF slide 视觉尺寸与当前 UI 基本一致。

若无法获得 parent viewport coordinates，停止并报告，不得悄悄改成 component-local coordinates。

### Output

建议：

```text
modules/ui/slide_viewport_component/
modules/system/slide_geometry.py
tests/test_slide_geometry.py
```

### Constraints

- 不重复显示第二张 slide；
- 不显著压缩 slide workspace；
- normalized AOI 仍是持久化 canonical representation；
- viewport geometry 只作为 ephemeral runtime state；
- geometry stale 时 fail safely。

### Acceptance

- manual rectangle 与当前功能一致；
- AOI overlay 对齐；
- resize、sidebar toggle、scroll、slide change 均生成新 revision；
- normalized AOI → viewport AOI 转换测试通过；
- visual manual review 确认主 slide 空间无明显退化。

---

## Checkpoint 2 — Live Runtime and Grid-Gaze Target Proposal

### Context

live runtime 已能接收 browser media、完成 VAD/STT 和 gaze grid，但当前会在自身 pipeline 中直接完成 target/tutor；最终产品需要它只产生 canonical proposal。

### Request

1. 将 media capture、master switch、camera preview 接入新主 UI；
2. sidebar 新增：
   - Mode: Manual / Live；
   - Master switch；
   - Confirmation policy；
   - AOI confidence threshold；
   - transport/runtime status；
3. camera preview 放在可折叠区域；
4. production sensing 复用现有 `GazePrediction` 的 grid 数据；
5. 使用 `resolve_grid_target(...) + SlideViewportGeometry` 生成 AOI proposal；
6. speech turn 完成后通过 `LatestProposalInbox` 发送：
   - STT transcript；
   - predicted AOI；
   - target confidence；
   - alternatives；
   - deck / slide / layout revision；
7. Streamlit poll 后将 transcript 自动填入现有 command input。

### Interaction source rules

```text
原始 live proposal:
mode = sensor_assisted
target.source = gaze_prediction
intent.source = speech_transcript

用户修改 transcript 或 target:
mode = hybrid
intent.source = typed_text（若 transcript 被编辑）
confirmation.source = manual_correction（若 target 被修改）
metadata 保留 original_speech_transcript 与 predicted_aoi_id
```

`IntentInput.source_confidence=None`，并添加简短注释说明未来 STT confidence 接口。

### Output

建议：

```text
modules/system/live_ui_bridge.py
```

### Constraints

- 保留 single-port HTTP transport；
- background threads 不修改 `st.session_state`；
- media handlers 不执行 VAD、STT、sensing 或 LLM；
- capture component 稳定挂载在 periodic fragment 外，fragment 只 poll runtime / inbox；
- one active speech turn；
- bounded queues 与 cleanup contract 不变；
- `LiveTutorAdapter` 不在 production path 中回答问题。

### Acceptance

- Manual mode 与原 UI 行为不回归；
- Live mode camera/mic、VAD、STT、gaze 都运行；
- transcript 自动进入 command input；
- gaze proposal 使用 viewport AOI geometry；
- slide/layout mismatch 不生成有效 target；
- low confidence / no target 时 UI 保留 top-k、whole slide 和 manual rectangle 入口；
- 选择前不调用 LLM。

---

## Checkpoint 3 — Unified Confirmation and Final LLM Workflow

### Context

`InteractionInput` 已支持：

```text
manual / sensor_assisted / hybrid
gaze_prediction
speech_transcript
automatic_high_confidence
manual_correction
```

因此不需要新建第二套 interaction schema。

### Request

实现两种 policy：

#### Always confirm

```text
live proposal
→ transcript 自动填入
→ 显示 predicted AOI + top-k
→ 用户确认或纠正
→ main_tutor_integration
```

#### Confidence-based auto

只有同时满足以下条件时自动确认：

- target confidence ≥ UI threshold；
- threshold 不低于 interaction contract minimum；
- predicted AOI 存在；
- geometry fresh；
- deck、slide、layout revision 一致；
- transcript 非空；
- 当前没有另一 active/pending interaction。

然后构造：

```text
ConfirmationInput(
    confirmed=True,
    source="automatic_high_confidence",
    confirmed_aoi_id=predicted_aoi_id,
)
```

若任一条件不满足，退回人工 confirmation。

### LLM execution

唯一调用：

```text
generate_main_tutor_response(...)
```

要求：

- API call 在 Streamlit/UI orchestration 层触发；
- 使用 interaction ID 防止 rerun 重复调用；
- API error 直接展示；
- provider error、response parse failure、grounding validation failure 在重试耗尽后均显示为可重试错误；
- 不使用 deterministic fallback；
- confirmed interaction 保留，可重试；
- answer、history、XAI、JSONL 使用同一 interaction ID。

### Output

- unified live/manual confirmation UI；
- auto-confirm policy；
- no-fallback API error path；
- unified history/XAI/logging。

### Constraints

- correction 永远覆盖 prediction；
- whole-slide/manual fallback 仍需显式用户选择；
- auto-confirm threshold 默认 `0.80`；
- current contract 的最低自动确认门槛仍为 `0.70`；
- 不复制 `main_tutor_integration`。

### Acceptance

自动测试覆盖：

1. Always confirm 不提前调用 LLM；
2. high confidence 自动确认并只调用一次；
3. low confidence 显示候选；
4. no gaze 不调用；
5. user correction 覆盖 predicted AOI；
6. transcript edit 进入 hybrid mode；
7. stale geometry 阻止 auto-confirm；
8. API failure 显示错误且无 mock answer；
9. rerun 不重复调用；
10. history/XAI 与 interaction ID 一致。

---

## Checkpoint 4 — End-to-End Acceptance and Release Readiness

### Request

在 AutoDL + 一个 SSH-forwarded port 上完成：

#### Manual mode

- upload real PDF；
- slide navigation；
- manual rectangle；
- confirmation；
- real LLM；
- history / XAI。

#### Live / Always confirm

- camera/mic；
- 说出 deictic request；
- STT 自动填入；
- gaze AOI proposal；
- 人工 correction；
- real LLM。

#### Live / Confidence-based auto

- high-confidence proposal 自动确认；
- 自动调用 real LLM；
- 低置信度自动退回人工；
- no-gaze 选择 whole slide 或 manual rectangle。

至少完成 5 个 live turns，覆盖：

1. high-confidence auto；
2. always confirm；
3. correction；
4. low confidence；
5. no valid gaze；
6. API error 后重试（可作为额外 turn）。

### Final validation

```bash
python -m compileall -q modules apps scripts tests
python -m unittest discover -s tests -v
python scripts/demo_tutor_loop.py
python evaluation/eval_reference_resolution.py
python evaluation/eval_scenario_outputs.py
git diff --check
```

并分别运行两个原分支的 UI/runtime smoke tests。

### Output

- final handoff；
- architecture / coordinate contract document；
- manual acceptance log；
- commit list；
- known limitations；
- working branch push。

### Constraints

- 不声称 continuous pixel-level gaze；
- 当前能力应描述为 coarse 3×3 viewport gaze targeting；
- `codex/ui-live-runtime-integration-v1` 是唯一融合交付分支和后续优化基线；
- 不提交 uploaded PDFs、raw audio/video、API keys；
- 不 merge main，不自动创建 PR。

### Completion definition

本阶段只有同时满足以下条件才完成：

- 新 UI 是唯一正式入口；
- Manual 和 Live mode 都可用；
- UI 与 runtime 使用同一 deck、slide 和 AOI；
- slide viewport geometry 可实时记录；
- 九宫格 gaze 在 viewport 坐标中匹配 AOI；
- STT 自动填入 UI；
- 两种 confirmation policy 可选；
- correction 覆盖 prediction；
- final answer 只经过 `main_tutor_integration`；
- API failure 不返回 deterministic answer；
- conversation history、XAI 与 JSONL 不重复；
- one-port live workflow 通过人工验收；
- full regression 通过。

---

## 7. Explicit Non-Goals

本阶段不处理：

- continuous `(x, y)` gaze point；
- gaze model retraining；
- eye-tracker-grade calibration；
- point-gaze abstraction hierarchy；
- general-purpose geometry/event framework；
- physical monitor coordinates；
- multi-user runtime；
- production authentication；
- mobile UI；
- emotion / confusion ground-truth claims；
- 重写 teammate UI；
- 重写 Member 1/2 algorithms。

下一阶段升级 gaze 时，只实现：

```text
PointGazeResolver
+ calibration
+ gaze_point_normalized / gaze_point_viewport
```

其余 UI、interaction、confirmation 和 LLM contract 保持不变。
