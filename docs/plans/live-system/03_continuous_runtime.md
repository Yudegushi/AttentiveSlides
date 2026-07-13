# 对话 3：Checkpoint 4–5 — Continuous Interaction Runtime

> 目标：构建连续交互核心，把 browser audio 自动分割为 speech turn，并将整个 speech window 的 sensing evidence 绑定到现有 canonical tutor pipeline。

## 1. 开始前读取

按 `00_global_contract.md` 第 4 节执行，必须先读：

- `handoffs/02_slide_sensing/handoff.md`
- handoff 指定的 provider/adapter/store commits 与 tests
- `modules/audio/transcriber.py`
- `modules/audio/faster_whisper_transcriber.py`
- `modules/audio/model_policy.py`
- `modules/interaction/speech_to_text.py`
- `modules/system/audio_adapters.py`
- `modules/system/adapters.py`
- `modules/system/pipeline.py`
- `modules/interaction/reference_resolver.py`
- `modules/logging/interaction_logger.py`
- Checkpoint 1 audio packet contract
- Checkpoint 3 `SensingSnapshotStore` window-query contract

确认 timestamp 使用同一 monotonic/epoch 语义；若 media 与 sensing clock 不同，先在 adapter boundary 正规化，不能在 context aggregation 中猜测。

## 2. Checkpoint 4 — Continuous audio turn detection

### 组件

```text
AudioRingBuffer
VADBackend protocol
VoiceTurnDetector
SpeechTurn
AudioWorker
```

首选 WebRTC-VAD-compatible backend，但必须通过 protocol 隔离。backend 选择服从 AutoDL dependency 证据，不能让 unit tests 下载模型或使用 microphone。

### 初始参数

```text
sample_rate = 16000
frame_ms = 30
pre_roll_ms = 300
speech_start_window_ms = 150
speech_end_silence_ms = 800
minimum_utterance_ms = 300
maximum_utterance_sec = 20
```

这些值是可配置初值。修改默认值必须在 handoff 记录真实 fixture/live 证据。

### 数据流

```text
browser audio packets
→ normalize mono PCM 16 kHz
→ fixed-size VAD frames
→ pre-roll ring buffer
→ speech_started / speech_ended / timeout
→ in-memory WAV or managed temporary file
→ existing transcribe_audio()
→ Transcript
```

不得重写 faster-whisper transcriber。temporary audio 在 transcription 后删除；默认不持久化 raw audio。

### 事件与失败语义

- silence 不产生 turn。
- 短噪声/短于 minimum 的片段被丢弃并可观测计数。
- maximum duration 强制 finalize，原因写入 `SpeechTurn` metadata。
- OFF/disconnect 立即取消 active turn 并清空敏感 buffer。
- STT failure 产生 recoverable turn error，不终止 monitoring session。
- audio overrun/drop 明确使当前 turn degraded 或 invalid，不能静默拼接。

### 建议文件

```text
modules/audio/streaming_vad.py
modules/audio/audio_ring_buffer.py
modules/audio/voice_turn_detector.py
modules/system/audio_worker.py
tests/test_audio_ring_buffer.py
tests/test_voice_turn_detector.py
tests/test_audio_worker.py
tests/fixtures/audio/
```

### Acceptance

deterministic PCM fixtures 覆盖 silence、single speech、two turns、short noise、pre-roll、trailing silence、maximum duration、chunk boundary、cancel、STT error 和 queue overrun。live microphone 说完后自动出现 transcript，不需要 start/stop/transcribe 按钮。

完成后独立 commit，建议 `feat: add continuous speech turn detection`。

## 3. Checkpoint 5 — Turn context and orchestration

### 组件与 ownership

```text
RuntimeState
TurnContextCollector
TutorTurnRunner
SystemController
```

`SystemController` 拥有 media/sensing/audio worker lifecycle 与单 active turn 约束；`TurnContextCollector` 只冻结/聚合 context；`TutorTurnRunner` 只把 canonical inputs送入现有 pipeline。不要把这些职责塞进 Streamlit session state。

### Turn freeze

speech start 时固定：

- `deck_id`
- `slide_id`
- speech start timestamp
- sensing window start = speech start 前 500 ms
- current AOI manifest/version identity

speech end 时固定 end timestamp。speech 期间 UI slide navigation 不得悄悄改变 turn 的 deck/slide；采用 start-time slide 作为 turn identity，并把 slide changed 作为可见 evidence/degradation。

### Gaze aggregation

1. 仅同一 slide ID 和同一 manifest identity。
2. 排除 stale、no-face、unknown-grid、invalid samples。
3. 按 `confidence × dwell contribution` 聚合 AOI。
4. top-1 为 predicted target，top-2 进入 alternatives。
5. evidence 不足时 `predicted_aoi_id=None`。
6. 结果仍交给现有 reference resolver 与 confirmation gate；collector 不自行决定最终回答。

aggregation threshold、dwell definition 与 tie-break 必须写成可测试纯逻辑，并在 handoff 记录。

### Pipeline reuse

`TutorTurnRunner` 必须复用：

```text
build_pipeline_input_bundle()
run_interaction_from_bundle()
run_interaction()
```

允许为 live input 增加小型 canonical provider/adapter，但不得复制 intent parsing、reference resolution、confirmation、tutor 或 logging 逻辑。

### Concurrency policy

- 同时只处理一个 active turn。
- 初始建议 processing/confirmation 时忽略新 speech 并暴露 `busy`，比隐藏的 queued speech 更可预测；若选择 single-item queue，必须证明不会把旧 slide/context 用到下一 turn。
- pending confirmation 时不产生 AOI-specific final answer。
- confirmation/correction 复用同一 frozen turn context；correction 覆盖 prediction。
- recoverable turn failure 返回 `MONITORING`；media source 失效才进入 `ERROR → STOPPED`。

### 建议文件

```text
modules/system/runtime_state.py
modules/system/turn_context.py
modules/system/live_turn_runner.py
modules/system/controller.py
tests/test_turn_context.py
tests/test_system_controller.py
tests/test_live_integrated_turn.py
```

### Deterministic E2E

```text
real PDF fixture
+ synthetic sensing snapshots
+ synthetic PCM speech turn
+ mock transcriber
+ MockLLM/template tutor
→ Transcript
→ window target aggregation
→ confirmation or answer
→ InteractionResult
→ JSONL log
→ MONITORING
```

覆盖 high-confidence、ambiguous top-2、no valid gaze、user correction、slide change during speech、STT failure、OFF during processing、disconnect 与 repeated start/stop。

完成后独立 commit，建议 `feat: orchestrate live tutor turns`。

## 4. 本对话停止边界

结束时 backend 应可用 synthetic inputs 连续执行多个 turns，并有确定的 state/lifecycle。不要在本对话把所有逻辑嵌入 product UI，也不要把 real API 设为默认测试依赖。

结束前更新：

`docs/plans/live-system/handoffs/03_continuous_runtime/handoff.md`

为对话 4 记录 controller public API、state transitions、thread ownership、busy policy、turn/context types、confirmation resume 方法、view-model 所需事件、commits、latency 与已知风险。
