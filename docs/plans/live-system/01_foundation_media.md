# 对话 1：Checkpoint 0–1 — Foundation and Browser Media

> 目标：独立验证所有高风险前提，建立可持续的 browser media transport；本对话不实现 slide/sensing canonical integration。

## 1. 开始前读取

严格按 `00_global_contract.md` 第 4 节执行，并额外阅读：

- `PROJECT_PROGRESS.md`
- `docs/audio_deployment.md`
- `docs/audio_merge_readiness.md`
- `docs/integration_sources.md`
- `docs/member1_member2_source.md`
- `docs/streamlit_xai.md`
- commits `353c033`、`ef6a1e7..705f1a2`
- `apps/streamlit_demo.py`
- `apps/streamlit_grounded_xai.py`
- `modules/audio/recording.py`
- `modules/audio/transcriber.py`
- `modules/audio/faster_whisper_transcriber.py`
- `modules/human_sensing/webcam_capture.py`
- `requirements-audio.txt`、`requirements-human-sensing-original.txt`、`requirements-slide.txt`

本对话没有上一阶段 handoff。把上述 progress/source/deployment 文档视为 legacy handoff，并在新 handoff 中指出其中已经过时的 LenovoLinux 环境描述。

## 2. Checkpoint 0 — AutoDL preflight and safe branch

共同分支已经由规划对话从 `feature/api-llm-pipeline@705f1a2` 创建。执行对话仍必须验证它，而不是重复创建另一个分支。

### 工作

1. `git fetch origin --prune`，确认 `main`、`integration-v100`、`feature/api-llm-pipeline` 是否变化。
2. 记录当前 branch、status、最近 20 个 commits、upstream 状态和 merge-base。
3. 记录 Python、conda、CUDA、GPU、磁盘与 dependency 状态；不得自动升级 torch/CUDA。
4. 检查 `streamlit`、`streamlit-webrtc`/候选 fallback dependency、OpenCV、MediaPipe、PyMuPDF、faster-whisper 与 VAD 候选是否可 import。
5. 运行 baseline tests 与现有 demos/evaluations，区分代码失败、缺 dependency、GPU/model/API 外部依赖。
6. 把结果写入 handoff；如需 dependency 文件变更，与 Checkpoint 1 的实际 transport 实现一起提交，不创建纯猜测 dependency。

### 必须记录的命令

```bash
git status --short --branch
git log --oneline --decorate -n 20
python -V
nvidia-smi
python -m unittest discover -s tests -v
python scripts/demo_tutor_loop.py
python evaluation/eval_reference_resolution.py
python evaluation/eval_scenario_outputs.py
git diff --check
```

如果 grounded API tests 默认需要真实 key，应修正测试隔离；不得把外部 API 变成 mandatory unit-test dependency。

### Checkpoint 0 acceptance

- 分支与起点可追溯；工作树没有被覆盖。
- baseline pass/fail、dependency gap、GPU/CUDA 状态有明确证据。
- 形成独立 commit，建议 `chore: audit AutoDL integration baseline`；若只产生 handoff/progress 文档，也必须保证内容是实际测量结果。

## 3. Checkpoint 1 — Browser video/audio transport gate

### 先做最小 probe

优先建立 `apps/media_transport_probe.py`，验证浏览器经 `ssh -N -L 8501:127.0.0.1:8501 AutoDL` 打开的 `http://localhost:8501` 能持续提供本地 camera/microphone。

建议边界：

```python
class BrowserMediaSource:
    def start(self) -> None: ...
    def stop(self) -> None: ...
    video_queue: bounded queue
    audio_queue: bounded queue
```

probe 必须显示 connection state、video FPS、audio chunk rate、last timestamps、queue depth/drop count 和 cleanup state；这些是 transport 证据，不是产品 UI。

### Transport 决策顺序

1. Primary：`streamlit-webrtc`。
2. 在 AutoDL + 单端口 SSH forwarding 上完成真实 browser smoke。
3. 若 ICE/media connection 无法稳定建立，记录可复现失败，不在 WebRTC 上无限调参。
4. 实现 single-port fallback：浏览器 component 将降采样 frame 与 PCM audio chunk 通过 Streamlit component channel 或同 origin HTTP transport 送入 8501。
5. 最终只保留一个默认 live transport；另一路径可保留为明确 fallback，但不能有两套不一致的 `BrowserMediaSource` contract。

### Queue 与 lifecycle 规则

- video queue 只保留最新少量 frames，consumer 落后时丢弃旧帧。
- audio queue 有明确 byte/time 上限；不能静默丢失导致 speech turn 拼接错误，必须记录 drop/overrun。
- callback 不执行 inference，不调用 `st.*`，不写 raw media。
- `start()`/`stop()` 幂等；OFF 后 2 秒内停止。
- refresh、disconnect、permission denied 和 component error 都能释放资源。
- 同一 Streamlit session/rerun 不创建重复 worker。

### 建议文件

```text
apps/media_transport_probe.py
modules/media/__init__.py
modules/media/browser_media_source.py
modules/media/media_packets.py
tests/test_browser_media_source.py
tests/test_media_queue_policy.py
docs/browser_media_runtime.md
```

具体路径可随现有结构小幅调整，但 transport contract、queue policy 与测试必须独立于 Streamlit UI。

### Verification

Automated：

- synthetic video/audio packet 的 bounded queue、latest-frame、ordering、drop count、idempotent start/stop、disconnect cleanup。
- tests 不申请真实 camera/microphone，不依赖 WebRTC network。
- 全量 regression tests 与 `git diff --check`。

Manual gate：

- browser 授权 camera/microphone。
- ON 后连续收到两类 media；OFF 后 2 秒内停止。
- 连续 3 分钟 queue 不增长失控。
- 页面刷新/断开后 cleanup。
- deployment command 与 transport 选择写入 `docs/browser_media_runtime.md`。

任何未执行 manual 项必须在 handoff 中写为 `not verified`，不能用 automated test 代替。

## 4. 本对话停止边界

本对话结束时只要求可靠地产生 browser packet queues。不要开始 MediaPipe inference、AOI conversion、VAD、STT orchestration 或 live product UI。

结束前更新：

`docs/plans/live-system/handoffs/01_foundation_media/handoff.md`

并为对话 2 明确记录：实际 transport、packet 类型/shape/timestamp、queue API、dependency 版本、运行命令、cleanup 语义、commit SHA 与未验证风险。
