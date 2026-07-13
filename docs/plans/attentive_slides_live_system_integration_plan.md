# AttentiveSlides 下一阶段开发规划
## Real Module Integration + Browser Media Runtime

> **执行环境**：AutoDL 云平台
> **代码仓库**：`Yudegushi/AttentiveSlides`
> **起始分支**：`origin/integration-v100`
> **目标**：将 Member 1 的 Slide/AOI、Member 2 的 Human Sensing、现有 Audio/STT 与 Member 3/4 interaction pipeline 组成一个可实际使用的连续交互系统。

---

## 0. 文档用途

本文件是下一阶段的执行计划。Codex 读取后应直接进入 goal mode，按 checkpoint 顺序实现，不需要重新提出一套总体架构。

Codex 仍需在开始前完成一次短暂 preflight，用于确认：

- AutoDL 本地仓库、分支和未提交修改；
- Python / CUDA / dependency 状态；
- 远端 `main` 与 `integration-v100` 是否发生变化；
- 本规划引用的代码接口是否仍存在。

只有出现以下情况时才暂停并重新规划：

1. 远端代码结构与本文假设明显不一致；
2. AutoDL 环境无法运行必要 dependency；
3. browser media transport 在 AutoDL 网络环境中无法建立，且 fallback 也不可行；
4. 需要破坏现有 canonical schemas 或 confirmation gate 才能继续。

---

## 1. 当前已确认状态

### 1.1 已完成

`main` 已包含：

- Member 3/4 的 adapter-backed interaction pipeline；
- intent parsing、reference resolution、adaptive policy；
- uncertainty-aware confirmation gate；
- slide-grounded tutor context；
- Streamlit mock demo；
- file-based `faster-whisper` STT；
- audio evaluation 与 JSONL logging。

`integration-v100` 已基于最新 `main`，并额外加入：

- `modules/slide/`：PDF parsing、slide rendering、OCR、AOI generation；
- `modules/human_sensing/`：camera source、face landmarks、head pose、gaze grid、AOI mapping、learning-state aggregation；
- Member 1/2 config、requirements 和独立 demo。

### 1.2 尚未完成

当前仓库还没有形成真实连续系统：

- Member 1/2 输出尚未接入 `modules/system/adapters.py`；
- system canonical schemas 与 Member 1/2 dataclasses 尚未统一映射；
- Streamlit UI 仍主要使用 mock gaze / learning-state；
- audio 仍是手动录制或上传后点击 transcription；
- 没有 background microphone monitoring、VAD、speech-end detection；
- 没有 master switch 和 runtime state machine；
- 默认 tutor 仍使用 `MockLLM`；
- cloud-side `cv2.VideoCapture(0)` 无法访问用户本地摄像头。

---

## 2. 本阶段最终用户流程

用户在 AutoDL 启动 Streamlit：

```bash
python -m streamlit run apps/streamlit_live.py \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless true
```

本地建立 SSH port forwarding：

```bash
ssh -N -L 8501:127.0.0.1:8501 AutoDL
```

用户浏览器打开：

```text
http://localhost:8501
```

浏览器负责访问本地 webcam 和 microphone，AutoDL 负责：

- slide parsing；
- MediaPipe / gaze processing；
- VAD 后的 STT；
- AOI reference resolution；
- LLM tutoring；
- logging 与 UI state。

目标交互：

```text
Upload PDF
→ select slide
→ turn master switch ON
→ browser continuously streams camera and microphone
→ system continuously updates gaze/AOI evidence
→ user starts speaking
→ system detects speech start
→ user stops speaking
→ system detects speech end
→ STT produces transcript
→ system combines transcript + speech-window gaze + slide AOIs
→ confident target: answer directly
→ uncertain target: request confirmation
→ return to monitoring after the turn
```

用户开启 master switch 后，不需要每次手动点击“开始录音”和“结束录音”。

---

## 3. Browser media 架构决定

### 3.1 不使用 cloud camera index 作为正式输入

正式 live path 禁止依赖：

```python
cv2.VideoCapture(0)
```

该调用只会寻找 AutoDL 服务器设备，不能访问用户浏览器所在电脑的摄像头。

`OpenCVCameraSource` 和 `RealSenseCameraSource` 保留用于：

- 本地硬件运行；
- video fixture；
- optional server-attached camera。

它们不是 cloud UI 的默认 media source。

### 3.2 两级 media transport

#### Primary：`streamlit-webrtc`

首先实现最小 browser video/audio streaming probe。浏览器页面通过 SSH tunnel 以 `localhost` 打开；camera 和 microphone permission 由本地浏览器授予。

Media callback 只做：

- frame/chunk 格式转换；
- timestamp；
- non-blocking push 到 bounded queue；
- 丢弃过旧数据。

Media callback 内禁止直接运行 MediaPipe、Whisper、LLM 或 `st.*`。

#### Fallback：single-port chunk transport

SSH 只转发一个 TCP port，WebRTC media connection 仍可能因 ICE / STUN / TURN 或 AutoDL 网络限制失败。

因此 Checkpoint 1 必须是 transport gate：

- WebRTC 在目标 AutoDL + SSH tunnel 环境中稳定工作：继续使用；
- WebRTC 无法建立：实现 browser component，将降采样 video frames 和 PCM audio chunks 通过现有 Streamlit/component channel 或同一 HTTP origin 发送，确保所有数据只经过 forwarded port 8501。

不允许绕过该问题，改回手动 upload 并宣称 live system 已完成。

---

## 4. 固定系统边界

### 4.1 Canonical schemas

`modules/common/schemas.py` 继续作为 system-level canonical schema。

Member 1/2 dataclasses 只能通过 adapter 转换，不能直接扩散到：

- `modules/system/pipeline.py`
- `modules/interaction/`
- `modules/tutor/`
- UI view model

必要新增字段必须：

- 有默认值；
- backward-compatible；
- 不破坏现有 mock/audio tests。

### 4.2 Runtime components

实现以下边界，名称可小幅调整，但职责不可混合。

```python
class BrowserMediaSource:
    start()
    stop()
    video_queue
    audio_queue

class RealSlideProvider(SlideProvider):
    load_deck(pdf_path)
    get_slide_frame(slide_id)

class HumanSensingAdapter:
    process_frame(frame, slide_frame)
    to_canonical_gaze(...)
    to_canonical_learning_state(...)

class SensingSnapshotStore:
    update(snapshot)
    latest_valid(slide_id, max_age_sec)
    query_window(slide_id, start_ts, end_ts)

class VoiceTurnDetector:
    accept_audio_chunk(chunk)
    poll_event()  # speech_started / speech_ended / timeout

class TurnContextCollector:
    begin_turn(start_ts, slide_id)
    finalize_turn(end_ts)
    collect_gaze_evidence(...)

class TutorTurnRunner:
    run(transcript, sensing_context, slide_context)

class SystemController:
    start()
    stop()
    handle_media_events()
    confirm_target(aoi_id)
```

### 4.3 Runtime state machine

```text
STOPPED
→ STARTING
→ MONITORING
→ SPEECH_ACTIVE
→ FINALIZING_AUDIO
→ PROCESSING_TURN
→ WAITING_CONFIRMATION   (only when required)
→ MONITORING
```

任何状态均可进入：

```text
ERROR
→ STOPPED
```

约束：

- `start()` 和 `stop()` 必须 idempotent；
- 同一 session 只允许一个 active speech turn；
- processing 时的新 speech 不得覆盖当前 turn；
- queue 必须有容量上限；
- stale frame / stale sensing snapshot 必须显式降级；
- browser disconnect、master switch OFF、页面关闭时必须释放 worker；
- 不长期保存 raw audio/video，除非用户显式开启 debug recording。

---

# 5. Checkpoints

## Checkpoint 0 — AutoDL Preflight and Safe Branch

### Context

远端 `integration-v100` 已包含最新 main 和 Member 1/2 import，但 AutoDL 本地仓库可能不是最新版，也可能有未提交工作。

### Request

1. 连接 SSH host `AutoDL`；
2. 定位仓库并审计 git state；
3. `git fetch origin --prune`；
4. 检查本地 branch 与 `origin/main`、`origin/integration-v100`；
5. 检查 Python、conda、CUDA、GPU 和 dependency；
6. 从 `origin/integration-v100` 创建独立工作分支或 worktree。

### Output

- preflight report；
- working branch，例如 `codex/live-system-integration-v1`；
- baseline test results；
- dependency gap list。

### Constraints

- 禁止 `git reset --hard`；
- 禁止 `git clean -fd`；
- 禁止覆盖本地未提交文件；
- 禁止直接修改或 merge `main`；
- 不自动升级 torch/CUDA build。

### Acceptance

以下命令均有记录：

```bash
git status --short --branch
git log --oneline --decorate -n 15
python -V
nvidia-smi
python -m unittest discover -s tests -v
python scripts/demo_tutor_loop.py
python evaluation/eval_reference_resolution.py
python evaluation/eval_scenario_outputs.py
```

---

## Checkpoint 1 — Browser Video/Audio Transport Gate

### Context

正式系统运行在 AutoDL，但输入设备位于用户本地浏览器。现有 `st.audio_input` 和 `st.camera_input` 只适合一次录音或一次截图，不满足连续监控。

### Request

新增最小 probe app，例如：

```text
apps/media_transport_probe.py
```

功能：

- master switch；
- browser webcam preview；
- browser microphone input；
- server 端显示 video FPS、audio chunk rate、last timestamp；
- bounded thread-safe queues；
- start / stop / disconnect cleanup；
- 连续运行至少 3 分钟。

先测试 `streamlit-webrtc`。若在单端口 SSH forwarding 下失败，按第 3.2 节实现 single-port fallback。

### Output

- 可运行 media transport；
- transport 选择及原因；
- `BrowserMediaSource`；
- transport smoke test；
- deployment command。

### Constraints

- callback 不执行模型 inference；
- callback 不调用 `st.*`；
- video queue 默认只保留最新少量 frames；
- audio queue 必须 bounded；
- 禁止 raw media 默认落盘；
- WebRTC 失败不得伪装成功。

### Acceptance

在本地浏览器通过 `http://localhost:8501`：

- 可授权 camera 和 microphone；
- master switch ON 后持续收到 video/audio；
- OFF 后 2 秒内停止并释放资源；
- 连续 3 分钟无 queue 无界增长；
- 页面刷新或断开后 worker 能清理；
- transport 路径和已知限制写入文档。

---

## Checkpoint 2 — Real Slide Provider

### Context

Member 1 已实现 PDF loading、rendering、embedded text extraction、OCR fallback 和 AOI generation，但 system pipeline 仍使用 mock manifest provider。

### Request

实现 `RealSlideProvider` 并接入现有 `SlideProvider` boundary。

必须完成：

1. PDF upload / load；
2. deck ID 管理；
3. slide rendering；
4. current slide text；
5. previous / next slide text；
6. Member 1 AOI → canonical `AOI`；
7. AOI selection policy；
8. explicit deck ID，不依赖 hard-coded slide 5。

AOI policy：

1. 优先有效 semantic / OCR text-block AOIs；
2. 自动 AOI 不可用时 fallback 到 rule AOIs；
3. 排除 footer；
4. 排除 `include_in_learning=False`；
5. `whole_slide` 不参与 gaze target competition，仅作为 explicit fallback；
6. overlapping AOIs 采用 deterministic priority；
7. AOI text 保留给 tutor context。

### Output

建议新增：

```text
modules/system/real_slide_provider.py
tests/test_real_slide_provider.py
tests/fixtures/slides/minimal_deck.pdf
docs/slide_provider_integration.md
```

### Constraints

- 不修改 Member 1 算法实现，除非发现明确 bug；
- data directory 必须可配置；
- tests 不共享 production manifest；
- OCR 只能作为 embedded text 不可用时的 fallback；
- 所有 bbox 为 normalized `[x1, y1, x2, y2]`。

### Acceptance

- 1 页、2 页和多页 PDF 均可读取；
- first / last slide neighbor context 正确；
- deck ID 不访问固定 slide 5；
- AOI IDs deterministic；
- pipeline 可使用 real deck store 运行现有 confirmation gate；
- existing tests 无回归。

---

## Checkpoint 3 — Human Sensing Adapter and Video Worker

### Context

Member 2 已输出 `GazePrediction`、`AOIPrediction` 和 `LearningState`，但这些不是 system canonical schemas。

### Request

实现：

```text
HumanSensingAdapter
SensingWorker
SensingSnapshotStore
```

处理流程：

```text
browser video frame
→ FaceLandmarkExtractor
→ head pose / gaze features
→ gaze grid
→ current slide AOIs
→ AOIPrediction
→ learning-state aggregation
→ canonical GazePrediction + LearningState
→ snapshot store
```

映射要求：

```text
AOIPrediction.predicted_aoi_id
AOIPrediction.confidence
AOIPrediction.stable_duration_sec
AOIPrediction.candidate_scores
→ canonical GazePrediction
```

`candidate_scores` 按 score 降序转换为 `alternative_targets`。

运行策略：

- media capture 可为 20–30 FPS；
- sensing inference 初始限制为约 5–10 FPS；
- worker 读取 latest frame，不处理积压旧帧；
- snapshot 包含 slide ID、source timestamp、processing timestamp；
- 默认 stale threshold 为 1.0 秒，可配置。

### Output

建议新增：

```text
modules/system/human_sensing_adapter.py
modules/system/sensing_worker.py
modules/system/sensing_snapshot_store.py
tests/test_human_sensing_adapter.py
tests/test_sensing_snapshot_store.py
```

### Constraints

- system pipeline 不 import Member 2 dataclasses；
- unit tests 使用 synthetic contracts，不启动 webcam；
- no-face、low-confidence、stale snapshot 必须有明确结果；
- 不把 observable signals 描述成真实 emotion、confusion 或 cognition；
- MediaPipe model 只初始化一次并在 stop 时释放。

### Acceptance

- synthetic AOIPrediction 映射测试通过；
- candidate ranking 正确；
- stale snapshot 被拒绝或降级；
- live video 能持续更新 gaze grid、AOI、confidence；
- slide changed 后旧 slide snapshot 不得用于新 turn；
- worker stop 后无残留 inference thread。

---

## Checkpoint 4 — Continuous Audio Turn Detection

### Context

现有 faster-whisper 已通过 file-based audio 验证，但每次需要手动录制和点击 transcription。目标是 master switch 开启后自动检测用户说话与结束。

### Request

实现：

```text
AudioRingBuffer
VoiceTurnDetector
SpeechTurn
AudioWorker
```

初始配置：

```text
sample_rate = 16000
frame_ms = 30
pre_roll_ms = 300
speech_start_window_ms = 150
speech_end_silence_ms = 800
minimum_utterance_ms = 300
maximum_utterance_sec = 20
```

VAD 使用独立 backend，首选 WebRTC VAD-compatible implementation；通过 protocol 隔离，便于替换。

流程：

```text
audio chunks
→ resample / mono PCM
→ VAD
→ speech_started
→ buffer voiced turn with pre-roll
→ trailing silence reaches threshold
→ speech_ended
→ create in-memory WAV / temporary file
→ existing transcribe_audio()
→ Transcript
```

### Output

建议新增：

```text
modules/audio/streaming_vad.py
modules/audio/audio_ring_buffer.py
modules/audio/voice_turn_detector.py
modules/system/audio_worker.py
tests/test_voice_turn_detector.py
```

### Constraints

- 不重写现有 faster-whisper transcriber；
- raw audio 默认不持久化；
- temporary audio 在 transcription 后删除；
- silence、短噪声、超时 turn 必须正确处理；
- master switch OFF 时立即取消 current turn；
- STT error 不得终止整个 monitoring session。

### Acceptance

使用 deterministic PCM fixtures 验证：

- silence 不触发 turn；
- speech + silence 产生一次 turn；
- 两段 speech 产生两次 turn；
- 短噪声被忽略；
- maximum duration 会强制 finalize；
- live microphone 说完后自动出现 transcript；
- 无需点击 start/stop recording 或 transcribe。

---

## Checkpoint 5 — Turn Context and Orchestration

### Context

系统需要把一个 speech turn 与正确的 slide 和 gaze evidence 绑定，而不是简单使用 speech-end 时刻的一帧 gaze。

### Request

实现：

```text
TurnContextCollector
TutorTurnRunner
SystemController
RuntimeState
```

speech turn 建立时固定：

- `deck_id`；
- `slide_id`；
- speech start/end timestamp；
- speech 前 500 ms 到 speech end 的 sensing window；
- current AOI manifest version。

gaze aggregation：

1. 仅使用同一 slide ID；
2. 排除 stale / no-face / unknown-grid samples；
3. 对 AOI 按 `confidence × dwell contribution` 聚合；
4. 最高分作为 predicted target；
5. 第二候选进入 `alternative_targets`；
6. evidence 不足时输出 `predicted_aoi_id=None`；
7. 最终仍交给现有 reference resolver 和 confirmation gate。

`TutorTurnRunner` 必须复用：

```text
build_pipeline_input_bundle()
run_interaction_from_bundle()
run_interaction()
```

不能复制 intent、reference resolution 或 tutor 逻辑。

### Output

建议新增：

```text
modules/system/runtime_state.py
modules/system/turn_context.py
modules/system/controller.py
modules/system/live_turn_runner.py
tests/test_turn_context.py
tests/test_system_controller.py
tests/test_live_integrated_turn.py
```

### Constraints

- 同时只处理一个 active turn；
- processing 期间的新 speech 采用明确 policy：忽略并提示 busy，或 bounded single-item queue；
- target confirmation 期间不得自动暴露 AOI-specific final answer；
- user correction 必须覆盖 prediction；
- turn failure 后回到 `MONITORING`，除非 media source 已失效。

### Acceptance

deterministic E2E：

```text
real PDF fixture
+ synthetic video sensing events
+ synthetic audio turn
+ MockLLM
→ transcript
→ target aggregation
→ confirmation or answer
→ InteractionResult
→ JSONL log
→ return to MONITORING
```

并验证：

- high confidence target；
- ambiguous top-2；
- no valid gaze；
- user correction；
- slide changes during speech；
- STT failure；
- master switch OFF during processing。

---

## Checkpoint 6 — Live Streamlit UI

### Context

现有 `apps/streamlit_demo.py` 是已验证 regression demo，不应被重写成不可测试的大型 live app。

### Request

保留现有 demo，新增：

```text
apps/streamlit_live.py
```

UI 必须包含：

- PDF upload；
- slide navigation；
- slide image；
- AOI overlay；
- master switch；
- media permission / connection state；
- runtime state；
- camera preview；
- latest gaze grid；
- predicted AOI；
- confidence；
- transcript；
- confirmation candidates；
- tutor response；
- error / latency summary；
- optional developer panel。

交互规则：

- master switch ON：启动 media source 和 controller；
- OFF：停止所有 worker；
- high-confidence turn：显示 response；
- uncertain turn：显示 candidate AOIs，用户确认后运行 final answer；
- manual transcript input 保留为 debug fallback；
- file audio input 保留为 regression fallback；
- UI rerun 不得重复初始化模型或创建重复 worker。

### Output

```text
apps/streamlit_live.py
modules/system/live_view_model.py
tests/test_live_view_model.py
docs/live_ui_usage.md
```

### Constraints

- 不删除 `apps/streamlit_demo.py`；
- 不在 UI 文件中实现核心 inference；
- 不在 callback 中修改非线程安全 session state；
- 不展示“用户困惑/疲劳”等未经验证结论；
- raw media preview 与 derived signals 明确区分。

### Acceptance

通过 SSH forwarding 实测：

1. 上传 PDF；
2. 开启 master switch；
3. camera 和 microphone 均运行；
4. 看向一个 AOI 并说“解释这个”；
5. 系统自动识别 speech end；
6. transcript 正确进入 pipeline；
7. target 正确或触发 confirmation；
8. 获得 grounded response；
9. 关闭 master switch 后资源释放；
10. 至少连续完成 5 个 turns，无需重启 app。

---

## Checkpoint 7 — Real LLM, Evaluation and Documentation

### Context

现有 `TutorAgent` 默认使用 `MockLLM`，`integration-v100` 只有独立 DashScope smoke script。

### Request

实现 `LLMClient` compatible 的 optional DashScope client：

```text
modules/tutor/dashscope_llm.py
```

要求：

- API key 仅从 environment / secrets 读取；
- tests 默认使用 `MockLLM`；
- API failure 有明确 UI error；
- prompt 继续使用 slide-grounded context；
- answer 记录 model、latency、used AOI 和 context IDs。

完成以下文档：

```text
PROJECT_PROGRESS.md
README.md
docs/member1_member2_integration.md
docs/browser_media_runtime.md
docs/continuous_interaction_design.md
docs/live_ui_usage.md
```

### Output

- optional real LLM path；
- final test report；
- known limitations；
- reproducible run commands；
- one integrated demo scenario。

### Constraints

- 不提交 API key；
- 不让 external API 成为 mandatory unit-test dependency；
- 不声称未测量的 gaze accuracy、VAD accuracy 或 learning effectiveness；
- 不把 system demo 结果当作 user study 结论。

### Acceptance

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

- browser media smoke；
- 5-turn live interaction；
- optional DashScope turn；
- log inspection；
- stop / restart lifecycle；
- error recovery。

---

## 6. Checkpoint 提交规则

每个 checkpoint 完成后：

1. 运行该 checkpoint tests；
2. 运行全部 regression tests；
3. 更新 progress document；
4. 单独 commit；
5. 不等待所有工作完成才提交一个巨大 commit。

建议 commit：

```text
chore: audit AutoDL integration baseline
feat: add browser media transport
feat: add real slide provider
feat: adapt live human sensing outputs
feat: add continuous speech turn detection
feat: orchestrate live tutor turns
feat: add live Streamlit interface
feat: add optional DashScope tutor client
docs: finalize live system integration guide
```

不要 merge 到 `main`。最终 push working branch 并报告 commit SHA。

---

## 7. 本阶段完成定义

本阶段只有同时满足以下条件才算完成：

- Member 1 real PDF/AOI 已进入 canonical pipeline；
- Member 2 live gaze/learning signals 已进入 canonical pipeline；
- browser webcam 和 microphone 可从本地传到 AutoDL；
- master switch 开启后可持续监控；
- speech start/end 自动检测；
- 每个 speech turn 自动触发 STT 和 tutor pipeline；
- gaze target 使用 speech-window evidence；
- uncertainty confirmation gate 保持有效；
- UI 可通过单个入口运行；
- existing mock/audio regression tests 不退化；
- system 能连续处理至少 5 个 live turns；
- master switch OFF 和 browser disconnect 能清理资源；
- 文档准确说明已实现、未实现与已知限制。

---

## 8. 明确不在本阶段处理

- pixel-level eye tracking；
- 精确 emotion / confusion recognition；
- multi-user session；
- production authentication；
- mobile adaptation；
- full TURN service production deployment；
- large-scale user study；
- 自动优化 gaze/VAD thresholds；
- 长期存储 raw audio/video；
- 重新设计 Member 1/2 核心算法。

这些工作只能在完整 system workflow 稳定后进入下一阶段。
