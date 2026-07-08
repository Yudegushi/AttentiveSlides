# AttentiveSlides：成员 3 与成员 4 同步启动规划

> 这里按模块名称为准：  
> - 成员 3：Voice、Intent 与 Multimodal Fusion  
> - 成员 4：Tutor Agent、System Integration 与 Evaluation  
>
> 本规划目标：让这两个系统层模块先形成一个可运行的端到端 dry-run pipeline，方便后续接入真实 AOI、gaze、STT、LLM 和 UI。

---

## 1. 核心判断

成员 3 和成员 4 应该同步推进，因为它们之间存在非常清晰的上下游关系：

```text
成员 3：Transcript + Gaze + LearningState + AOI + History
→ ResolvedQuery

成员 4：ResolvedQuery + Slide Context + Prompt Policy
→ TutorResponse + UI State + Log
```

所以第一步不是先接 Whisper，也不是先做完整 UI，而是先固定两个模块之间的数据契约：

```text
Mock Slide / AOI
+ Mock Gaze / LearningState
+ Text Transcript
→ ResolvedQuery
→ TutorContext
→ TutorResponse
→ InteractionLog
```

只要这个链路跑通，后续真实模块都只是替换输入源。

---

## 2. 第一阶段目标

第一阶段做一个可运行的 mock-driven system loop：

```text
用户文本输入：“解释这个”
→ intent parser 判断 intent = explain
→ reference resolver 根据 gaze / AOI 得到 resolved_aoi_id
→ adaptive policy 得到回答策略
→ context retriever 取出 AOI / slide / history 上下文
→ tutor agent 生成回答
→ logger 记录完整交互
```

第一阶段暂时不做：

- 真实 Speech-to-Text；
- 真实 webcam；
- 真实 slide parser；
- 复杂 autonomous agent；
- 完整前端 UI；
- 正式实验评估。

---

## 3. 成员 3 第一件事：ResolvedQuery Pipeline

成员 3 第一件事是做：

```text
Text Transcript
+ Mock GazePrediction
+ Mock LearningState
+ Mock AOI list
+ InteractionHistory
→ ResolvedQuery
```

### 3.1 需要实现的文件

```text
modules/interaction/intent_parser.py
modules/interaction/reference_resolver.py
modules/interaction/adaptive_policy.py
modules/interaction/interaction_history.py
modules/interaction/resolved_query.py
```

### 3.2 Intent Parser

MVP 支持：

```text
explain
compare
quiz
summarize
simplify
step_by_step
review
break
```

第一版使用 rule-based parser。它需要输出：

```text
intent
confidence
has_deictic_reference
explicit_target_hint
```

示例：

```text
“解释这个”
→ intent = explain
→ has_deictic_reference = true
→ explicit_target_hint = None

“解释右边这个图”
→ intent = explain
→ has_deictic_reference = true
→ explicit_target_hint = right_figure

“总结这一页”
→ intent = summarize
→ has_deictic_reference = false
→ explicit_target_hint = whole_slide
```

### 3.3 Reference Resolver

核心优先级：

```text
explicit target hint > gaze target > whole_slide > click_required
```

第一版规则：

```text
如果用户明确说“右边的图 / 左边文字 / 底部公式”
→ 使用 explicit target

如果用户说“这个 / this / here”
→ 使用 gaze predicted AOI

如果用户说“总结这一页”
→ 使用 whole_slide

如果 gaze confidence 太低
→ 不硬猜，返回 click_required
```

### 3.4 Confirmation Policy

建议阈值：

```text
confidence >= 0.70
→ confirmation_mode = confirm_one

0.45 <= confidence < 0.70
→ confirmation_mode = choose_top2

confidence < 0.45
→ confirmation_mode = click_required
```

### 3.5 Adaptive Policy

输入：

```text
learning_state
intent
history
resolved_aoi_id
```

输出：

```text
normal
short_recap
simpler_explanation
step_by_step
ask_confirmation
review_question
```

第一版规则：

```text
screen_facing_score < 0.5
→ ask_confirmation

yawn_count_last_3min >= 2
→ short_recap

same_aoi_repeated_questions >= 2
→ simpler_explanation

stable_duration_sec >= 5 and intent == explain
→ step_by_step

intent == review
→ review_question

otherwise
→ normal
```

注意：系统不能说“你累了”或“你困惑了”。只能输出策略，让 Tutor Agent 用更保守的方式表达，例如：

```text
我可以先给你一个更短的 recap。
这个区域可能值得复习一下，要不要我换一种更简单的方式解释？
```

---

## 4. 成员 4 第一件事：Tutor Agent Dry-Run Pipeline

成员 4 第一件事是做：

```text
ResolvedQuery
+ Mock Deck / AOI Manifest
+ InteractionHistory
→ TutorContext
→ TutorResponse
→ InteractionLog
```

### 4.1 需要实现的文件

```text
modules/tutor/context_retriever.py
modules/tutor/prompt_template.py
modules/tutor/llm_tutor.py
modules/tutor/tutor_agent.py
modules/logging/interaction_logger.py
```

### 4.2 Context Retriever

输入：

```text
deck_id
slide_id
resolved_aoi_id
history
```

输出：

```text
TutorContext
```

`TutorContext` 至少包括：

```text
current_slide_text
current_aoi_text
neighbor_slide_text
resolved_query
interaction_history
adaptive_strategy
```

第一版用 mock deck，不等成员 1 的 slide parser。

### 4.3 Prompt Template

Prompt 需要固定边界：

```text
只能基于给定 slide context 回答；
如果需要外部知识，必须说明是补充背景；
回答中文，关键术语保留英文；
不要声称知道用户真实情绪；
不要声称知道用户真实注意力；
根据 adaptive_strategy 调整回答方式；
回答要围绕 resolved_aoi_id，而不是泛泛总结整页。
```

### 4.4 Tutor Agent

这里建议写一个轻量自定义 `TutorAgent`，不要一开始接 OpenClaw / Hermes 这类通用 agent 框架。

第一版 `TutorAgent` 只需要做三件事：

```text
1. 根据 ResolvedQuery 调用 ContextRetriever
2. 根据 intent + adaptive_strategy 选择 Prompt Template
3. 调用 LLMClient 或 MockLLM 生成 TutorResponse
```

建议接口：

```python
class TutorAgent:
    def answer(self, resolved_query, deck_state, history) -> TutorResponse:
        ...
```

### 4.5 TutorResponse

输出至少包括：

```text
query_id
answer
response_mode
active_recall_question
adaptive_suggestion
used_context
safety_notes
```

示例：

```json
{
  "query_id": "q_001",
  "response_mode": "explain",
  "answer": "这个区域主要在解释 SHAP 如何把模型预测分解成不同 feature 的贡献。",
  "active_recall_question": "如果一个 feature 的 SHAP value 为正，它通常表示什么？",
  "adaptive_suggestion": null
}
```

### 4.6 Interaction Logger

第一版必须记录 JSONL，因为后面实验和 report 需要。

每次交互记录：

```text
query_id
timestamp
slide_id
transcript
intent
predicted_aoi_id
resolved_aoi_id
confirmed_aoi_id
target_confidence
needs_confirmation
user_corrected
adaptive_strategy
response_mode
latency_ms
```

---

## 5. 两个模块的同步 demo

第一阶段最终要能运行：

```bash
python scripts/demo_tutor_loop.py
```

这个脚本跑完整链路：

```text
mock slide / AOI
mock gaze / learning_state
text transcript
→ 成员 3 ResolvedQuery
→ 成员 4 TutorResponse
→ log event
```

### Demo Case 1：普通解释

```text
transcript = "解释这个"
gaze predicted_aoi = right_figure
confidence = 0.76
```

期望：

```text
intent = explain
resolved_aoi_id = right_figure
confirmation_mode = confirm_one
response_mode = explain
```

### Demo Case 2：总结整页

```text
transcript = "总结这一页"
```

期望：

```text
intent = summarize
resolved_aoi_id = whole_slide
confirmation_mode = none
response_mode = summarize
```

### Demo Case 3：中等置信度，需要二选一

```text
transcript = "考我一下这个概念"
confidence = 0.55
alternative_targets = right_figure, bottom_caption
```

期望：

```text
intent = quiz
confirmation_mode = choose_top2
response_mode = quiz
```

### Demo Case 4：明确目标覆盖 gaze

```text
transcript = "解释右边这个图"
gaze confidence = 0.30
```

期望：

```text
explicit_target_hint = right_figure
resolved_aoi_id = right_figure
confirmation_mode = none
```

### Demo Case 5：adaptive strategy 生效

```text
transcript = "解释这个"
screen_facing_score = 0.35
```

期望：

```text
adaptive_strategy = ask_confirmation
TutorResponse 使用更谨慎表达
```

---

## 6. Agent 选择建议

建议第一版写一个轻量自定义 `TutorAgent`，不要直接使用 OpenClaw / Hermes 这种通用 agent framework。

原因：

1. 本项目的 agent 不需要高度自主执行任务，它只需要在 slide tutoring 场景中完成受控的 context retrieval、prompt selection、response generation 和 logging。
2. 课程评分更看重 methodology、interaction loop、evaluation 和 critical reflection。自定义 agent 更容易解释和评估。
3. 通用 agent 框架会引入大量与项目无关的复杂性，例如长期 memory、外部工具调用、权限、安全边界、部署配置。
4. 本项目需要可解释、可纠正、可记录的教学反馈。过强的 autonomous agent 反而会削弱系统可控性。

推荐定位：

```text
不是 autonomous general-purpose agent，
而是 task-bounded tutoring agent。
```

也就是：

```text
TutorAgent = ContextRetriever + PromptPolicy + LLMClient + ResponseFormatter + Logger
```

如果后期想在 report 里写得更像 agent，可以称它为：

```text
A task-bounded slide-grounded tutoring agent
```

---

## 7. 第一阶段目录结构

```text
attentive_slides_plus/
│
├── modules/
│   ├── common/
│   │   └── schemas.py
│   │
│   ├── interaction/
│   │   ├── intent_parser.py
│   │   ├── reference_resolver.py
│   │   ├── adaptive_policy.py
│   │   ├── interaction_history.py
│   │   └── resolved_query.py
│   │
│   ├── tutor/
│   │   ├── context_retriever.py
│   │   ├── prompt_template.py
│   │   ├── llm_tutor.py
│   │   └── tutor_agent.py
│   │
│   └── logging/
│       └── interaction_logger.py
│
├── data/
│   └── mock_deck/
│       └── mock_aoi_manifest.json
│
├── scripts/
│   └── demo_tutor_loop.py
│
└── tests/
    ├── test_intent_parser.py
    ├── test_reference_resolver.py
    ├── test_context_retriever.py
    └── test_tutor_agent.py
```

---

## 8. 给 Codex 的第一条任务

```text
Implement the first mock-driven system loop for AttentiveSlides member 3 and member 4.

Scope:
- Member 3: Voice / Intent / Multimodal Fusion
- Member 4: Tutor Agent / System Integration

Implement:

1. modules/common/schemas.py
Define dataclasses:
AOI, GazePrediction, LearningState, Transcript, IntentResult, ResolvedQuery, TutorContext, TutorResponse, InteractionLogEvent.

2. modules/interaction/intent_parser.py
Implement rule-based parsing for:
explain, compare, quiz, summarize, simplify, step_by_step, review, break.
Also detect deictic references and explicit target hints:
right figure, left text, bottom formula, whole slide.

3. modules/interaction/reference_resolver.py
Implement:
explicit target hint > gaze target > whole_slide > click_required.
Implement confirmation policy:
>=0.70 confirm_one,
0.45-0.70 choose_top2,
<0.45 click_required.

4. modules/interaction/adaptive_policy.py
Implement strategy selection:
normal, short_recap, simpler_explanation, step_by_step, ask_confirmation, review_question.

5. modules/tutor/context_retriever.py
Use a mock AOI manifest and mock slide text to create TutorContext from ResolvedQuery.

6. modules/tutor/prompt_template.py
Create prompt templates for:
explain, compare, quiz, summarize, simplify, step_by_step, review, short_recap.
Prompts must be slide-grounded and must not claim true emotion, fatigue, or attention state.

7. modules/tutor/llm_tutor.py
Implement a MockLLM first.
Optionally support real LLM through an abstract LLMClient interface, but do not require API keys for tests.

8. modules/tutor/tutor_agent.py
Implement TutorAgent.answer(resolved_query, deck_state, history) -> TutorResponse.

9. modules/logging/interaction_logger.py
Write each interaction as JSONL.

10. scripts/demo_tutor_loop.py
Run five fixed demo cases:
- explain this with high-confidence gaze
- summarize this slide
- quiz this concept with medium confidence
- explicit right figure target overriding low gaze confidence
- low screen-facing score triggering ask_confirmation

11. tests/
Add basic tests for intent parsing, reference resolution, context retrieval, and tutor agent output.

Do not implement real webcam, real STT, real slide parser, or full UI yet.
Focus on deterministic outputs and stable interfaces.
```

---

## 9. Mac 与 4060 游戏本建议

这个第一阶段可以直接在 Mac 上做，因为它主要是 Python 逻辑、schemas、mock data、parser、prompt、logger 和 tests。

后续接入 faster-whisper、webcam、gaze calibration、final demo 时，建议放到 4060 游戏本上。最终 demo 机器最好固定，因为摄像头、屏幕尺寸、坐姿、麦克风环境都会影响结果。

推荐：

```text
Mac：写系统逻辑、prompt、tests、mock demo
4060 游戏本：跑 STT、webcam、gaze calibration、最终 demo 和录屏
GitHub：同步代码
```
