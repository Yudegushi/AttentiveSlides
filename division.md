# AttentiveSlides 项目 Agent Brief

> Source: `四人分工与接口设计.pdf`  
> Purpose: 给后续 coding / planning / debugging agent 快速理解项目目标、模块边界、接口和数据流。本文是精简版，不是 PDF 逐字转写。

## 1. 项目一句话定义

本项目是一个 Human-Centered AI slide learning assistant：用户看着课件某个区域并说“解释这个”时，系统结合 slide AOI、webcam gaze / learning-state signals、voice intent 和 LLM Tutor，生成基于课件内容的解释、总结、quiz 或复习建议。

核心闭环：

```text
Slide 结构化
-> Webcam 估计 gaze / learning-state signals
-> Speech 识别用户 intent
-> Multimodal fusion 解析目标 AOI
-> LLM Tutor 生成 grounded learning feedback
-> UI 展示、用户确认/修正、日志记录与评估
```

## 2. 关键约束与项目 claim

1. 系统不是普通 slide QA，而是 gaze + voice + learning-state signal 驱动的 Human-Centered AI 学习辅助系统。
2. 不能声称准确识别用户真实情绪、真实认知状态或真实注意力。
3. 更严谨的表述是检测 `observable learning-state signals`，例如：face detected、screen-facing score、yawn signal、eye closure、head down、long fixation on same AOI。
4. LLM Tutor 必须基于 slide context 回答；如果需要外部知识，必须显式说明。
5. Adaptive strategy 只能温和表达，例如“我可以帮你做一个更短的 recap”，不能直接说“你困了/你困惑了”。

## 3. 四个模块分工

| Member | Module | Main Responsibility |
|---|---|---|
| 1 | Slide & AOI | PDF/PPT slide 解析、slide 渲染、OCR、AOI 生成与手动修改 |
| 2 | Human Sensing | Webcam capture、face landmarks、gaze/head pose、yawn、eye closure、learning-state signal |
| 3 | Voice & Multimodal Fusion | STT、intent parsing、deictic reference detection、reference resolution、adaptive policy |
| 4 | Tutor Agent & System Integration | Context retrieval、LLM Tutor、UI、logging、evaluation、report/presentation integration |

## 4. Module 1: Slide & AOI

### Goal

把上传的 PDF/PPT slides 转换成系统可用的结构化 slide data。

### MVP Tasks

- 上传 PDF slides。
- 每页 slide 渲染为图片。
- 每页 slide 做 OCR 文本提取。
- 每页 slide 生成 AOI。
- 支持手动修改 AOI：name、type、bbox、text、delete、add。
- 给 gaze 模块提供 AOI bbox。
- 给 tutor 模块提供 OCR text + AOI text。

### AOI Examples

```text
title
left_block
right_block
top_region
bottom_region
whole_slide
right_figure
bottom_formula
center_table
```

### Files

```text
modules/slide/slide_parser.py
modules/slide/aoi_manager.py
modules/slide/ocr.py
data/aoi_manifest.json
data/slide_images/
```

### Interfaces

```python
load_deck(pdf_path) -> deck_id
render_slide(deck_id, slide_id) -> slide_image_path
get_slide_aois(deck_id, slide_id) -> list[AOI]
get_slide_text(deck_id, slide_id) -> str
update_aoi(deck_id, slide_id, aoi_id, bbox, aoi_type, text) -> AOI
```

### Output Schema

```json
{
  "slide_id": 5,
  "slide_image_path": "data/slide_images/slide_005.png",
  "ocr_text": "This slide explains SHAP values...",
  "aois": [
    {
      "aoi_id": "right_figure",
      "bbox": [0.55, 0.18, 0.95, 0.78],
      "type": "figure",
      "text": "SHAP force plot"
    }
  ]
}
```

`bbox` 建议使用 normalized coordinates: `[x1, y1, x2, y2]`，范围 `[0, 1]`。

## 5. Module 2: Human Sensing

### Goal

通过 webcam 粗粒度估计用户正在看哪里，并检测可观察的 learning-state signals。

### MVP Tasks

- OpenCV webcam capture。
- MediaPipe Face Mesh / Face Landmarker 提取 face、eye、mouth landmarks。
- Gaze / head pose 输出九宫格区域。
- 9-point calibration，训练简单 personalized classifier。
- 检测 yawn signal：mouth opening / mouth aspect ratio + duration threshold。
- 检测 eye closure：eye aspect ratio + duration threshold。
- 检测 head down / screen facing。
- 聚合 learning-state signal。

### Gaze Grid

```text
top_left      top_center      top_right
middle_left   middle_center   middle_right
bottom_left   bottom_center   bottom_right
```

### Files

```text
modules/human_sensing/webcam_capture.py
modules/human_sensing/gaze_estimator.py
modules/human_sensing/calibration.py
modules/human_sensing/face_state_detector.py
modules/human_sensing/learning_state_aggregator.py
```

### Interfaces

```python
extract_face_landmarks(frame) -> FaceLandmarks
estimate_head_pose(face_landmarks) -> HeadPose
predict_gaze_grid(frame, calibration_profile) -> GazePrediction
map_gaze_to_aoi(gaze_prediction, aois) -> AOIPrediction
detect_learning_state(frame, face_landmarks, history) -> LearningState
```

### Output Schema to Module 3 / UI

```json
{
  "timestamp": 1710000000.32,
  "gaze_prediction": {
    "slide_id": 5,
    "gaze_grid": "right_middle",
    "predicted_aoi_id": "right_figure",
    "confidence": 0.72,
    "stable_duration_sec": 2.3
  },
  "learning_state": {
    "face_detected": true,
    "screen_facing_score": 0.86,
    "yawn_detected": false,
    "yawn_count_last_3min": 1,
    "eyes_closed": false,
    "eye_closure_duration_sec": 0.1,
    "head_down": false,
    "fatigue_signal_score": 0.23,
    "possible_review_needed": false
  }
}
```

## 6. Module 3: Voice, Intent & Multimodal Fusion

### Goal

理解用户说了什么、想做什么，并结合 gaze / AOI / learning-state 判断用户想问哪个 slide 区域。

### MVP Tasks

- Speech-to-text，可用 `faster-whisper`；保留 text input fallback。
- Intent parsing。
- Deictic reference detection：检测“这个/那个/这里/this/that/this figure/this formula”。
- Reference resolution：融合 transcript、intent、gaze prediction、AOI list、learning-state、history。
- Confirmation strategy：根据 target confidence 决定直接使用、显示 top-1/top-2、要求点击修正。
- Adaptive policy：根据 learning-state signal 调整回答策略。

### Supported Intents

| Intent | Example |
|---|---|
| `explain` | 解释这个 / explain this |
| `compare` | 这个和上一个有什么区别 |
| `quiz` | 考我一下这个概念 |
| `summarize` | 总结这一页 |
| `simplify` | 讲简单一点 |
| `step_by_step` | 一步一步解释 |
| `review` | 我该复习哪里 |
| `break` | 我有点累了 |

### Confirmation Policy

```text
explicit target in speech
-> use explicit target

implicit reference + high gaze confidence
-> show predicted AOI and ask confirmation

implicit reference + medium confidence
-> show top-2 AOI candidates

low confidence
-> ask user to click AOI or rephrase
```

### Adaptive Policy Examples

| Signal | Strategy |
|---|---|
| normal | `normal_explanation` |
| repeated yawn signal | `short_recap` / break suggestion |
| long fixation on same AOI | `step_by_step` |
| repeated questions on same AOI | `simpler_explanation` |
| low screen-facing score | pause / ask confirmation |
| `possible_review_needed = true` | generate review question |

### Files

```text
modules/interaction/speech_to_text.py
modules/interaction/intent_parser.py
modules/interaction/reference_resolver.py
modules/interaction/adaptive_policy.py
modules/interaction/interaction_history.py
```

### Interfaces

```python
transcribe_audio(audio_path) -> Transcript
parse_intent(transcript) -> IntentResult
detect_deictic_reference(transcript) -> bool
resolve_reference(intent_result, gaze_prediction, learning_state, aois, history) -> ResolvedQuery
select_adaptive_strategy(learning_state, intent_result, history) -> AdaptiveStrategy
```

### Output Schema to Module 4

```json
{
  "query_id": "q_001",
  "slide_id": 5,
  "transcript": "解释这个",
  "intent": "explain",
  "resolved_aoi_id": "right_figure",
  "target_confidence": 0.74,
  "needs_confirmation": true,
  "adaptive_strategy": "normal",
  "evidence": [
    "用户使用了指代词：这个",
    "gaze_grid = right_middle",
    "predicted_aoi = right_figure",
    "stable_duration = 2.3s"
  ],
  "alternative_targets": [
    {"aoi_id": "right_figure", "score": 0.74},
    {"aoi_id": "bottom_caption", "score": 0.51}
  ]
}
```

## 7. Module 4: Tutor Agent & System Integration

### Goal

把 slide data、gaze / learning-state、resolved query 整合为完整 demo 系统，并负责评估与汇报。

### MVP Tasks

- Context retriever：取当前 AOI、当前 slide OCR、上一页/下一页文本、history、question、adaptive strategy。
- LLM Tutor prompt design。
- Tutor response generation。
- Streamlit / Gradio UI 集成。
- 用户确认 / 修正 AOI。
- 日志记录。
- 实验评估与结果分析。

### LLM Prompt Constraints

```text
只能基于给定 slide context 回答。
如果需要外部知识，必须明确说明。
回答中文，关键术语保留英文。
不要声称知道用户真实情绪。
不要声称知道用户真实注意力。
根据 adaptive strategy 调整回答长度和风格。
```

### Response Modes

```text
explain
compare
summarize
quiz
simplify
step_by_step
review
short_recap
```

### UI Panels

1. `Slide Viewer`: 当前 slide、AOI 框、predicted AOI highlight、用户点击修正。
2. `Human-State Panel`: face detected、gaze grid、predicted AOI、confidence、yawn、eye closure、screen-facing score。
3. `Interaction Panel`: transcript、intent、resolved AOI、confirm / correct。
4. `Tutor Response Panel`: explanation、simplified explanation、review suggestion、active recall question。

### Files

```text
modules/tutor/context_retriever.py
modules/tutor/llm_tutor.py
modules/tutor/prompt_template.py
modules/logging/interaction_logger.py
app.py
evaluation/eval_aoi_accuracy.py
evaluation/eval_learning_state.py
evaluation/eval_usability.py
```

### Interfaces

```python
retrieve_context(deck_id, slide_id, resolved_aoi_id, history) -> TutorContext
generate_tutor_response(tutor_context, intent, adaptive_strategy) -> TutorResponse
log_interaction(event) -> None
render_ui_state(slide, aois, gaze, learning_state, resolved_query, response) -> None
```

### Tutor Response Schema

```json
{
  "query_id": "q_001",
  "answer": "这个图展示的是 SHAP 如何解释模型预测结果...",
  "active_recall_question": "如果一个特征的 SHAP value 为正，它通常表示什么？",
  "adaptive_suggestion": null
}
```

### Log Schema

```json
{
  "query_id": "q_001",
  "timestamp": 1710000000.32,
  "slide_id": 5,
  "transcript": "解释这个",
  "intent": "explain",
  "predicted_aoi_id": "right_figure",
  "confirmed_aoi_id": "right_figure",
  "target_confidence": 0.74,
  "user_corrected": false,
  "learning_state": {
    "yawn_detected": false,
    "fatigue_signal_score": 0.23
  },
  "adaptive_strategy": "normal",
  "response_mode": "explain"
}
```

## 8. End-to-End Data Flow

```text
1. Module 1 outputs Slide + AOI
   -> Module 2 uses AOI bbox for gaze-to-AOI mapping
   -> Module 4 uses OCR/AOI text for tutor context

2. Module 2 outputs GazePrediction + LearningState
   -> Module 3 uses them for multimodal fusion
   -> Module 4 displays them in UI

3. Module 3 outputs ResolvedQuery
   -> Module 4 retrieves context and calls Tutor

4. Module 4 outputs TutorResponse
   -> UI displays answer, question, recap, review suggestion
   -> logger stores interaction event
```

## 9. Recommended Directory Structure

```text
attentive_slides_plus/
├── app.py
├── config.yaml
├── modules/
│   ├── slide/
│   │   ├── slide_parser.py
│   │   ├── aoi_manager.py
│   │   └── ocr.py
│   ├── human_sensing/
│   │   ├── webcam_capture.py
│   │   ├── gaze_estimator.py
│   │   ├── calibration.py
│   │   ├── face_state_detector.py
│   │   └── learning_state_aggregator.py
│   ├── interaction/
│   │   ├── speech_to_text.py
│   │   ├── intent_parser.py
│   │   ├── reference_resolver.py
│   │   ├── adaptive_policy.py
│   │   └── interaction_history.py
│   ├── tutor/
│   │   ├── context_retriever.py
│   │   ├── llm_tutor.py
│   │   └── prompt_template.py
│   └── logging/
│       └── interaction_logger.py
├── data/
│   ├── uploaded_decks/
│   ├── slide_images/
│   ├── aoi_manifest.json
│   ├── calibration_profiles/
│   └── logs/
├── evaluation/
│   ├── eval_aoi_accuracy.py
│   ├── eval_learning_state.py
│   ├── eval_usability.py
│   └── analysis.ipynb
└── README.md
```

## 10. Evaluation Plan

Minimum experiments:

1. `AOI Grounding Accuracy`: 用户说“解释这个”时，系统预测 AOI 是否正确。
2. `Learning-State Signal Detection`: yawn、eye closure、head down、screen-facing 等信号是否稳定。
3. `Interaction Efficiency / Usability`: 与 click-only 或 text-only baseline 对比交互效率和主观可用性。

## 11. Integration Timeline

| Phase | Time | Goal | Owner |
|---|---:|---|---|
| 1 | Day 1-2 | 题目、system claim、related work | All |
| 2 | Day 3-4 | slide viewer、AOI schema、OCR 初版 | Member 1 |
| 3 | Day 4-6 | gaze/head pose、yawn、eye closure 初版 | Member 2 |
| 4 | Day 6-7 | STT、intent parser、deictic reference detection | Member 3 |
| 5 | Day 7-9 | reference resolver、adaptive policy | Member 3 |
| 6 | Day 9-11 | LLM Tutor、UI integration | Member 4 |
| 7 | Day 11-13 | pilot test、bug fixing | All |
| 8 | Day 14+ | formal experiment、report、presentation、demo video | All |

## 12. Report / Presentation Ownership

### Report

| Member | Section |
|---|---|
| 1 | Slide representation、AOI design、slide parsing、OCR、manual annotation |
| 2 | Human sensing、gaze/head pose、face-state detection、yawning、privacy risk |
| 3 | Voice interaction、intent parsing、multimodal fusion、reference resolution、adaptive strategy |
| 4 | Tutor agent、UI integration、evaluation design、results、discussion、limitation |

### Presentation

| Member | Focus |
|---|---|
| 1 | slide AOI 如何生成，系统如何理解课件内容 |
| 2 | webcam 如何估计 gaze 和 learning-state signals |
| 3 | 用户说“解释这个”时，系统如何融合 gaze + voice 找到目标区域 |
| 4 | AI Tutor 回答、system demo、实验结果、Human-Centered AI reflection |

## 13. MVP Implementation Priority

优先保证 end-to-end demo 跑通，不要一开始追求复杂模型。

Recommended MVP order:

```text
1. PDF -> slide image + simple AOI manifest
2. Manual AOI editing / correction
3. Webcam -> coarse gaze grid -> AOI mapping
4. Text input fallback + rule-based intent parser
5. Reference resolver with confidence + confirmation
6. LLM Tutor with grounded prompt
7. Streamlit/Gradio UI
8. Interaction logger
9. Pilot test and evaluation scripts
```

## 14. Agent Notes

- AOI schema、ResolvedQuery schema、Log schema 是集成核心，开发时优先保持字段稳定。
- Gaze 不需要精确 eye tracking，MVP 目标是 coarse grounding。
- Intent parser 可以先 rule-based；后续再换 LLM / classifier。
- Adaptive policy 不要做医学/心理判断，只做支持策略选择。
- Tutor response 的质量关键在 context retriever 和 prompt constraints。
- UI 必须允许用户确认或修正 target AOI，否则 gaze 错误会直接污染回答。
