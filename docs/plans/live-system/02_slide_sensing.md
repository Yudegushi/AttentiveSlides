# 对话 2：Checkpoint 2–3 — Slide and Sensing Canonical Pipeline

> 目标：统一处理“视觉输入到 canonical pipeline”，让真实 PDF/AOI 与 browser video sensing 通过 adapter 边界进入现有 interaction pipeline。

## 1. 开始前读取

按 `00_global_contract.md` 第 4 节执行，必须先读：

- `handoffs/01_foundation_media/handoff.md`
- handoff 中列出的 Checkpoint 0–1 commits 与 transport files
- `modules/common/schemas.py`
- `modules/system/adapters.py`
- `modules/system/pipeline.py`
- `modules/tutor/context_retriever.py`
- `modules/slide/slide_parser.py`
- `modules/slide/ocr.py`
- `modules/slide/aoi_manager.py`
- `modules/human_sensing/contracts.py`
- `modules/human_sensing/calibration.py`
- `modules/human_sensing/gaze_estimator.py`
- `modules/human_sensing/face_state_detector.py`
- `modules/human_sensing/learning_state_aggregator.py`
- transport packet/queue contract from Checkpoint 1
- `tests/test_system_adapters.py`、`tests/test_system_pipeline.py`

先确认 Member 1/2 import 源 commits 与当前代码差异；不要重新导入上游目录覆盖已有 integration work。

## 2. Checkpoint 2 — RealSlideProvider

### 责任边界

实现一个 production provider，继续满足现有 `SlideProvider` / `SlideFrame` boundary。它负责 deck lifecycle、rendered slide、current/neighbor text 与 canonical AOI，不负责 gaze 或 UI。

必须消除 `ProviderBackedDeckStore.deck_id` 通过固定 `get_slide_frame(5)` 推断 deck 的行为。live path 必须在 load deck 时得到 explicit deck ID。

### 数据流

```text
PDF path/upload bytes
→ configurable deck store
→ Member 1 parser/rendering
→ embedded text; OCR only when embedded text unavailable
→ Member 1 AOI candidates
→ deterministic selection/filtering
→ canonical modules.common.schemas.AOI
→ SlideFrame / ProviderBackedDeckStore
```

### AOI policy

1. 优先有效 semantic/PDF/OCR text-block AOI。
2. 自动 AOI 不可用时 fallback 到 rule AOI。
3. 排除 footer 与 `include_in_learning=False`。
4. `whole_slide` 不参与 gaze target competition，只作为 explicit fallback。
5. overlap 使用稳定、可测试的 priority；排序与 ID 在重复 load 时 deterministic。
6. bbox 全部为 normalized `[x1, y1, x2, y2]`。
7. AOI text 保留给 tutor grounding；不把 source-specific metadata 扩散进 canonical pipeline。

### 建议文件

```text
modules/system/real_slide_provider.py
tests/test_real_slide_provider.py
tests/fixtures/slides/minimal_deck.pdf
docs/slide_provider_integration.md
```

fixture 应覆盖 1 页与至少 2 页的 neighbor boundary；多页行为可由同一生成器/fixture 验证。tests 使用临时 data directory，不共享 production manifest，也不要求 OCR binary/network 才能通过默认路径。

### Acceptance

- 1 页、2 页、多页 PDF load。
- first/last neighbor text 正确。
- explicit deck ID；无 hard-coded slide 5。
- AOI IDs/filter/priority deterministic。
- existing confirmation gate 能用 real provider 执行。
- Member 1 算法除明确、有 regression test 的 bug 外不修改。

完成后独立 commit，建议 `feat: add real slide provider`。

## 3. Checkpoint 3 — HumanSensingAdapter, worker and snapshot store

### 责任边界

实现：

```text
HumanSensingAdapter
SensingWorker
SensingSnapshotStore
```

`modules/system/pipeline.py` 不得 import Member 2 dataclass。adapter 是唯一 conversion boundary。

### 数据流

```text
BrowserMediaSource latest video packet
→ FaceLandmarkExtractor / head pose / gaze features
→ gaze grid
→ current slide AOIs
→ Member 2 AOIPrediction + LearningState
→ HumanSensingAdapter
→ canonical GazePrediction + LearningState
→ timestamped snapshot store
```

### 映射

- `predicted_aoi_id`、`confidence`、`stable_duration_sec` 直接进入 canonical gaze。
- `candidate_scores` 按 score 降序转换为 `alternative_targets`；tie-break 必须 deterministic。
- snapshot 同时记录 slide ID、source timestamp、processing timestamp 与 validity/no-face reason。
- 默认 stale threshold 1.0 秒，可配置。
- no-face、unknown-grid、low-confidence、slide mismatch 和 stale 都有明确降级，不用虚构 AOI。

### Worker 策略

- capture 可 20–30 FPS，初始 sensing inference 约 5–10 FPS。
- worker 读取 latest frame，不追赶积压旧帧。
- MediaPipe/model 每个 worker 初始化一次，stop 时释放。
- worker error 可见且可停止，不留下 inference thread。
- slide change 后旧 slide snapshot 不可进入新 turn。

### 建议文件

```text
modules/system/human_sensing_adapter.py
modules/system/sensing_worker.py
modules/system/sensing_snapshot_store.py
tests/test_human_sensing_adapter.py
tests/test_sensing_snapshot_store.py
tests/test_sensing_worker.py
```

### Verification

- synthetic Member 2 contracts 的完整 mapping；不启动 webcam。
- candidate ranking/tie-break。
- snapshot latest-valid 与 time-window query。
- stale/no-face/slide mismatch rejection。
- latest-frame/drop behavior 与 clean stop。
- real provider + synthetic sensing 能走现有 confirmation gate。
- 全量 regression tests 与 `git diff --check`。

Manual live video 只验证持续更新 grid/AOI/confidence 与 lifecycle；不在本 checkpoint 声称 gaze accuracy。

完成后独立 commit，建议 `feat: adapt live human sensing outputs`。

## 4. 本对话停止边界

结束时系统应能从 browser video 得到可查询的 canonical sensing snapshots，并从 real PDF 得到 canonical slide/AOI。不要实现 VAD、speech turn、controller 或 live product UI。

结束前更新：

`docs/plans/live-system/handoffs/02_slide_sensing/handoff.md`

为对话 3 明确记录 provider 构造方式、deck/slide lifecycle、snapshot schema、timestamp clock、window query API、stale policy、worker ownership、commits 和性能观察。
