# AttentiveSlides 项目规划 Guidance

> **项目暂定题目**  
> **AttentiveSlides: A Low-Cost Gaze-Grounded AI Tutor for Slide-Based Learning**  
> 副标题可选：**Using Webcam-Based Visual Attention and Voice Intent for Uncertainty-Aware Human-AI Tutoring**

---

## 0. 文档用途

这份文档记录当前阶段对 AIAA 3800 Human-Centered Artificial Intelligence 课程 project 的项目规划。后续开发、report 写作、presentation 准备、Codex 辅助实现、跨对话继续讨论，都应以此作为初始 guidance。

本项目应被理解为一个 **Human-Centered AI application system**，而不是一个新模型研究项目。核心目标不是提出新的 gaze estimation model 或 LLM model，而是设计、实现并评估一种低成本、可解释、可纠正的 **gaze-and-voice grounded learning interaction**。

---

## 1. 项目定位

### 1.1 一句话定义

**AttentiveSlides** 是一个基于笔记本摄像头和语音输入的 slide-learning AI tutor。用户阅读课件时，不需要显式输入“第几页第几个图”或“右下角公式”，而是可以看着某个 slide 区域说：

- “解释这个。”
- “这个和上一个方法有什么区别？”
- “考我一下这个概念。”
- “为什么这里要这么做？”

系统用 **coarse gaze / head pose** 推断用户正在关注的 slide region，再结合 speech intent 和 slide content 生成 grounded explanation。

更严格的项目表述是：

> AttentiveSlides explores a low-cost gaze-and-voice interaction design for slide-based learning, where gaze provides implicit visual reference and speech provides explicit learning intent.

### 1.2 不应该如何定位

不要把项目说成：

> “我们做了一个 AI 课件讲解器。”

这个说法过弱，因为现有 AI learning assistant / document QA / multimodal assistant 已经可以基于课件回答问题。你们真正要做的不是“AI 会讲课件”，而是：

> **让 AI tutor 获得用户当前 visual attention context，从而理解用户说的“这个 / 那个 / this / that”到底指向 slide 的哪个区域。**

### 1.3 核心交互范式

项目核心交互是：

```text
Look = implicit reference
Speech = explicit learning intent
AI = grounded tutoring response
```

也可以概括为：

> **Look-to-Ask：用户用目光选择上下文，用语音表达意图。**

---

## 2. 为什么这是 Human-Centered AI 项目

这个项目需要紧扣课程三条主线，而不是单纯做一个工具。

| HAI 主线 | AttentiveSlides 中的具体体现 |
|---|---|
| **AI for understanding human** | 用 webcam 估计用户 gaze / head pose，理解用户正在关注 slide 的哪个区域 |
| **Human-AI interaction** | 用 “look + ask” 替代繁琐文本描述，让用户自然地用“这个 / 那个”与 AI 互动 |
| **Human-AI coexistence** | 系统显式展示自己推断的 target、confidence 和 evidence，并允许用户纠正，避免黑箱误解 |

所以项目主 claim 应该是：

> **We design and evaluate a gaze-grounded interaction loop for slide-based AI tutoring.**

而不是：

> “We build an AI tutor that explains slides.”

---

## 3. Related Work 与 Gap

正式 report 中需要做扎实 related work。当前可按以下框架组织。

### 3.1 已有产品类型

#### 3.1.1 Source-grounded learning assistant

代表：NotebookLM、ChatPDF、文档问答类 AI assistant。

这些系统通常可以：

- 上传 PDF / notes / slides；
- 基于材料回答问题；
- 总结内容；
- 生成学习材料或问答。

这说明：

> **“上传课件并让 AI 回答问题”本身不新。**

#### 3.1.2 Multimodal live assistant

代表：Gemini Live 等支持 camera / screen sharing / voice interaction 的系统。

这些系统说明：

> **“看屏幕或摄像头内容，用语音问 AI”也不是完全空白。**

#### 3.1.3 Presentation / document AI assistant

代表：Microsoft Copilot in PowerPoint、各种 slide summarization / document QA 工具。

这些系统通常可以：

- summarize slides；
- explain selected content；
- generate presentation outline；
- answer questions about document content。

但问题是：

> 用户往往需要通过文本描述、截图、鼠标点击或明确位置指令来指定 target content。

### 3.2 已有研究方向

正式 report 可调研以下研究方向：

- **GazeGPT**：用 eye tracking 让 large multimodal model 理解用户正在注意的对象。
- **GazePointAR**：在 AR voice assistant 中，用 gaze / pointing / conversation history 消解 “this / that” 的模糊指代。
- **Gaze-grounded learning assistant / gaze-aware tutoring**：用 gaze 判断 learner 可能关注或困难的位置，并提供 retrospective assistance。
- **Adaptive learning / JITAI / attention-aware AIED**：把用户状态或注意力信号用于动态学习支持。

这些研究说明：

> gaze-aware AI tutor 不是完全新的研究空白。

因此本项目不能 claim “首创 gaze-aware tutoring”。更合理的 application-level gap 是：

> Existing gaze-aware systems often rely on eye trackers, smart glasses, AR devices, or egocentric gaze overlays. AttentiveSlides explores a low-cost laptop-webcam version for slide-based learning, with coarse AOI grounding, uncertainty display, and user correction.

### 3.3 本项目的合理 Gap

正式报告中可写成：

> Current AI learning assistants can answer questions about uploaded slides, but they usually do not know where the learner is visually attending. When learners ask deictic questions such as “explain this figure” or “why is this formula important,” they must still explicitly describe, click, or crop the target region. AttentiveSlides explores a low-cost gaze-and-voice interaction design in which webcam-based coarse gaze estimates provide implicit reference, speech provides learning intent, and the system makes its target inference explicit and correctable.

---

## 4. 项目 Contribution

建议最终 report 中只写三条 contribution，避免夸大或碎片化。

### Contribution 1 — Low-cost gaze-grounded reference resolution for slides

实现一个 laptop-webcam pipeline，把 coarse gaze / head-pose signals 映射到当前 slide 的 AOI（Area of Interest），使用户可以提出 “explain this / 解释这个” 这类 deictic questions，而不必显式描述位置。

### Contribution 2 — Uncertainty-aware human-AI tutoring loop

系统不会默默假设 target region 正确，而是显示：

- predicted AOI；
- confidence；
- supporting evidence；
- correction option。

用户可以在生成回答前确认或纠正 target。这个设计体现 human-in-the-loop 和 XAI / AI safety。

### Contribution 3 — Slide-grounded learning actions

系统支持与学习相关的 action：

- explain；
- compare；
- summarize；
- quiz；
- optional teach-back feedback。

回答基于 selected AOI 和 nearby slide context，而不是泛泛聊天。

---

## 5. 系统要做什么

### 5.1 用户流程

用户打开系统后上传一份 PDF slides。系统渲染每页 slide，并为每页生成若干 **AOI（Area of Interest）**，例如 title、figure、formula、table、bullet block。

用户阅读 slide 时，摄像头模块持续估计粗粒度 gaze / head direction。用户按下语音按钮或使用 wake phrase 后提问。系统把语音转成文本，识别 intent，然后结合当前 gaze AOI、当前 slide content 和历史上下文生成回答。

核心流程：

```text
User opens slide 12
→ system renders slide and detects AOIs
→ user looks at right-side figure
→ user says “explain this”
→ system estimates AOI = right-side figure, confidence = 0.72
→ system displays: “I think you mean the right-side figure. Confirm?”
→ user confirms or corrects
→ LLM explains that AOI using slide-grounded content
→ system logs gaze target, question, answer, correction
```

### 5.2 为什么必须有 confirmation / correction

Laptop webcam 的 gaze estimation 不可能达到专业 eye tracker 精度。因此项目不能假装系统能精确知道用户看哪个公式。

正确策略是：

> 把不确定性显式暴露出来，并让用户参与 disambiguation。

这不是缺点，而是 human-centered design：

- AI 不强行猜；
- 用户知道系统为什么这样判断；
- 用户可以纠正；
- 错误 target 不会直接导致错误讲解。

---

## 6. 功能范围

### 6.1 MVP 必须完成

MVP 只做四件事。

#### 1. Slide AOI parsing

系统能把 PDF / PPT slides 渲染出来，并为每页生成 AOI。

建议初版支持：

- whole slide；
- title region；
- left block；
- right block；
- bottom region；
- manually annotated AOI。

不要一开始追求完美 automatic layout understanding。

#### 2. Coarse gaze grounding

系统用 webcam 估计用户正在看屏幕的 coarse region：

```text
left / center / right × top / middle / bottom
```

然后映射到当前 slide 的 AOI。

目标是 coarse AOI grounding，不是 pixel-level gaze tracking。

#### 3. Voice intent parsing

支持 4 个基本 intent：

| Intent | 示例 |
|---|---|
| explain | “解释这个” / “explain this” |
| compare | “这个和上一个有什么区别？” / “compare this with the previous one” |
| quiz | “考我一下这个概念” / “quiz me on this” |
| summarize | “总结这一页” / “summarize this slide” |

#### 4. Grounded response + uncertainty UI

每次回答前显示：

- predicted target AOI；
- confidence；
- evidence；
- correction option。

确认后，系统基于当前 AOI 和 slide context 生成回答。

### 6.2 Stretch Goals

完成 MVP 后可选做：

1. **Teach-back mode**  
   用户对某页用自己的话复述，系统检查遗漏点和错误理解。

2. **Review trace**  
   记录用户多次回看的 AOI 和提问历史，生成 session review。

3. **Confusion marker**  
   根据长时间停留、重复回看、追问等行为，标记 possible review-needed region。注意不要直接说“用户困惑”，只能说 observable signals suggest this region may need review。

4. **Comparison across slides**  
   用户说“和上一个方法比”，系统自动找上一张相关 slide 或上一次交互对象。

5. **Bilingual explanation**  
   中文解释，关键 English terms 保留，适合课程学习场景。

---

## 7. 技术架构

### 7.1 总体 Pipeline

```text
Frontend / UI
  ├── Slide viewer
  ├── Webcam preview
  ├── AOI overlay
  ├── Voice input
  └── Tutor response panel

Backend pipeline
  ├── Slide parser
  ├── AOI manager
  ├── Gaze/head-pose estimator
  ├── Speech-to-text
  ├── Intent parser
  ├── Context retriever
  ├── LLM tutor
  └── Interaction logger
```

建议本地部署为主。4060 8GB 足够跑 MediaPipe、Whisper small/base、PDF rendering、Streamlit/Gradio。LLM 生成部分可用 API，也可预留 local fallback。

---

## 8. 模块设计与模型选择

### 8.1 Slide Parsing / AOI Module

#### 推荐工具

- PDF rendering：PyMuPDF / pdf2image
- PPT 转 PDF：LibreOffice headless，或直接要求用户上传 PDF
- OCR：PaddleOCR / EasyOCR / Tesseract
- AOI 生成：
  - MVP：rule-based + manual correction
  - Stretch：OCR boxes + layout grouping

#### 实际建议

优先要求用户上传 PDF，并允许手动 AOI correction。项目重点不在 PPT layout parsing，而在 gaze-grounded interaction。

#### AOI 数据结构示例

```json
{
  "slide_id": 12,
  "aoi_id": "right_figure",
  "bbox": [0.55, 0.18, 0.95, 0.78],
  "type": "figure",
  "text": "CAM heatmap visualization...",
  "neighbor_context": ["slide 11", "slide 13"]
}
```

---

### 8.2 Gaze / Head-Pose Module

#### 推荐工具

- MediaPipe Face Landmarker
- MediaPipe Face Mesh
- OpenCV
- scikit-learn

#### 目标

实现 laptop-webcam-based **coarse gaze / head-pose estimation**。

不要写成 accurate eye tracking。更严谨的说法是：

> webcam-based coarse gaze / head-pose estimation for AOI-level reference grounding.

#### 可提取特征

- face presence；
- head yaw / pitch / roll；
- iris / eye landmarks；
- eye center relative position；
- screen-facing confidence；
- coarse gaze grid：left / center / right × top / middle / bottom。

#### Calibration

建议做 9-point calibration：

1. 系统显示 9 个点；
2. 用户依次看每个点 2 秒；
3. 记录 face landmarks / iris position / head pose features；
4. 训练一个轻量分类器，把 feature 映射到 3×3 screen grid。

模型选择：

- baseline：rule-based threshold；
- better：Logistic Regression / Random Forest / KNN；
- 每个用户单独 calibration，不做跨用户训练。

#### HAI 价值

Personalized calibration 是重要设计点：

> 不用一套 universal threshold 判断所有用户，而是根据个体差异建立个人 gaze baseline。

---

### 8.3 Speech-to-Text / Intent Module

#### 推荐模型

- Whisper tiny/base/small
- faster-whisper

#### 部署建议

- 本地运行 faster-whisper `base` 或 `small`；
- 不必做真正 streaming；
- 可以录音 3–8 秒后转写；
- 保留 keyboard text input fallback。

#### Intent Parsing

MVP 中不需要复杂模型，可用 rule-based parser：

| Intent | 触发词 |
|---|---|
| explain | explain / 解释 / 讲一下 / what is this |
| compare | compare / 区别 / 和……相比 / difference |
| quiz | quiz / 考我 / test me |
| summarize | summarize / 总结 / main point |

复杂 query 可交给 LLM 做 intent classification，但必须保留 rule fallback。

---

### 8.4 Context Retriever

为了减少 LLM hallucination，Tutor 不应该只靠 general knowledge。回答必须基于 slide content。

#### Context 包括

- selected AOI text；
- current slide OCR text；
- previous / next slide text；
- lecture title / section；
- user question；
- confirmed target AOI；
- optional course-specific glossary。

#### 检索方式

MVP：

```text
current AOI + current slide + adjacent slides
```

Stretch：

```text
embedding retrieval from all slide chunks
```

可使用 sentence-transformers 或 API embedding。

---

### 8.5 LLM Tutor Module

#### 推荐部署

| 模块 | 首选 | fallback |
|---|---|---|
| STT | faster-whisper local | keyboard text input |
| Gaze | MediaPipe + calibrated classifier | mouse click AOI |
| LLM | GPT API / Gemini API | Ollama 小模型 / template response |
| Slide parsing | PyMuPDF + OCR | manual AOI annotation |

#### Prompt 约束

LLM prompt 应强制 source-grounded、uncertainty-aware：

```text
You are a slide-based tutor.
Use only the provided slide context and clearly mark any external background.
The user is asking about the confirmed AOI.
Do not pretend certainty when AOI confidence is low.
Answer in Chinese, preserve key English terms.
Return:
1. Direct explanation
2. Why it matters
3. Relation to nearby slides
4. One active-recall question
```

回答应像 tutor，不要像论文摘要器。建议默认输出中文，关键术语保留 English。

---

## 9. UI / Demo 设计

推荐 Streamlit 或 Gradio。

### 9.1 UI 四块区域

1. **Slide viewer**  
   显示当前 slide 和 AOI overlay。

2. **Webcam panel**  
   显示 face landmarks / gaze grid / confidence。

3. **Interaction panel**  
   显示 voice transcription、detected intent、predicted AOI。

4. **Tutor panel**  
   显示 explanation、active recall question、correction option。

### 9.2 Demo 流程

准备一个 90 秒左右的清晰 demo。

示例流程：

1. 打开 Lecture 12 XAI slide。
2. 用户看着 LIME 图，说：“解释这个。”
3. 系统预测 right AOI，显示 confidence，用户确认。
4. 系统解释 LIME。
5. 用户看着 SHAP 表格，说：“它和上一个有什么区别？”
6. 系统用 current AOI + previous interaction 解释 LIME vs SHAP。
7. 打开 session summary，展示用户问过哪些 AOI 和系统建议复习哪些部分。

Presentation 中最好准备：

- live demo；
- prerecorded demo backup；
- failure case demo；
- correction loop demo。

---

## 10. 实验设计

不要试图证明“学习成绩显著提升”。暑期项目样本小，claim 不应过强。建议做两个主要实验，一个可选实验。

---

### 10.1 Experiment 1: AOI Grounding Accuracy

#### 目的

证明 webcam-based gaze grounding 在受控 slide AOI 上有基本可用性。

#### 设计

- 准备 10–15 张 slides；
- 每张 3–5 个 AOI；
- 参与者先做 9 点 calibration；
- 系统给出 target AOI 提示，例如 “look at the right figure and ask explain this”；
- 记录 predicted AOI vs ground-truth AOI。

#### 对比方法

1. head-pose only；
2. eye / iris feature only；
3. head + eye personalized classifier。

#### 指标

- top-1 AOI accuracy；
- top-2 AOI accuracy；
- confidence calibration；
- latency；
- failure cases：glasses、lighting、off-center camera、small AOI。

#### 注意

这个实验不需要证明 eye tracking 精确。只证明 **AOI-level reference grounding** 是否可用。

---

### 10.2 Experiment 2: Interaction Efficiency / Usability

#### 目的

证明 gaze + voice 可以降低 reference specification cost。

#### 对比条件

| Condition | 用户如何指定 target |
|---|---|
| Text-only | 用户打字：“请解释第 7 页右侧图” |
| Click-to-ask | 用户鼠标点击 AOI，再提问 |
| Look-to-ask | 用户看 AOI 并语音问 “解释这个” |

#### 任务

每个用户完成 6–9 个 slide question tasks。

#### 指标

- task completion time；
- number of words in query；
- target selection success rate；
- correction frequency；
- perceived naturalness；
- perceived effort；
- trust / controllability。

#### 可能结果

不要预设 look-to-ask 全面胜出。更真实的结论可能是：

- look-to-ask 比 text-only 更自然，query 更短；
- click-to-ask target accuracy 更高；
- look-to-ask 对粗 AOI 可用，但对小公式 / 密集 slide 容易失败；
- uncertainty confirmation 能减少错误回答。

这种结果反而更可信。

---

### 10.3 Optional Experiment 3: Learning Support Quality

#### 目的

轻量评估 tutor feedback 是否有用。

#### 设计

让用户使用系统学习 5–10 分钟，然后填写问卷。

#### 指标

- explanation usefulness；
- active recall question usefulness；
- whether correction improved trust；
- whether gaze grounding reduced friction；
- perceived learning support。

#### 注意

这个实验只能作为 qualitative evaluation，不要 claim 大幅提升 learning outcomes。

---

## 11. 四人分工

分工应围绕系统闭环，而不是每个人各做一个孤立功能。

| 成员 | 负责模块 | 具体工作 | Report Contribution |
|---|---|---|---|
| Member 1 | Slide & AOI System | PDF rendering、AOI schema、manual/automatic AOI editing、slide text extraction | Human data representation: slide content / AOI representation |
| Member 2 | Gaze Grounding | MediaPipe webcam capture、calibration、coarse gaze classifier、confidence score | Human behavior modeling: gaze/head-pose to AOI |
| Member 3 | Voice & Intent | audio recording、Whisper transcription、intent parser、query history | Multimodal interaction: speech intent + reference resolution |
| Member 4 | Tutor Agent & Evaluation | context retrieval、LLM prompt、UI integration、logging、experiments | Human-AI interaction design + evaluation + critical reflection |

每个成员都要能在 presentation 中讲自己模块。

---

## 12. 开发计划

建议两周内完成 MVP，之后进入实验和 report。

| 阶段 | 时间 | 目标 |
|---|---|---|
| Phase 1 | Day 1–2 | 定题、确定 claim、完成 related work table、确定 demo slides |
| Phase 2 | Day 3–5 | Slide viewer + AOI annotation + basic LLM explanation |
| Phase 3 | Day 5–7 | MediaPipe gaze/head pose + 9-point calibration + AOI prediction |
| Phase 4 | Day 7–9 | Whisper transcription + intent parser + interaction history |
| Phase 5 | Day 9–11 | UI integration：look-to-ask complete loop |
| Phase 6 | Day 11–13 | 做 AOI accuracy 和 usability pilot，修 bug |
| Phase 7 | Day 14+ | 正式实验、整理 figures/tables、写 report 和 slides |

关键里程碑：

> 第 7 天必须有能跑的 end-to-end demo。后续所有 stretch goal 都不能影响主 demo。

---

## 13. Report 结构建议

正式 report 建议按以下结构写。

### 1. Introduction

讲问题：

> AI tutors know slides but not learner’s visual focus.

讲目标：

> low-cost gaze-and-voice grounded slide tutoring.

### 2. Related Work

分三类：

1. source-grounded AI tutors；
2. multimodal live assistants；
3. gaze-aware contextual AI。

明确 gap：

> low-cost laptop-webcam + slide AOI + uncertainty-aware correction。

### 3. System Design

用一个 pipeline figure 讲清楚：

```text
slide AOI → gaze grounding → speech intent → context retrieval → tutor answer → correction log
```

### 4. Implementation

写清楚：

- MediaPipe；
- Whisper；
- PyMuPDF / OCR；
- LLM API；
- UI framework；
- data logging。

### 5. Experiments

写 AOI accuracy 和 interaction efficiency / usability。

### 6. Results

放表格、图、failure cases。不要只放成功案例。

### 7. Discussion

重点写：

- human-centered design；
- uncertainty and correction；
- user control；
- privacy；
- limitation；
- failure cases；
- future work。

### 8. Conclusion

不要夸大。可以说：

> This project presents a low-cost prototype and design exploration for gaze-grounded slide-based tutoring.

### 9. Author Contributions

四人贡献明确写出。

---

## 14. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| Webcam gaze 不准 | target AOI 错误 | coarse AOI + top-2 candidates + confirmation |
| Slide layout 太复杂 | AOI parser 失败 | MVP 支持 manual AOI annotation |
| Whisper 转写错误 | intent 错误 | 保留 text input fallback |
| LLM 胡说 | tutor 不可靠 | source-grounded context + external background 标注 |
| 用户觉得被监控 | HAI 伦理风险 | 本地 webcam processing，不存原始视频，只存 features |
| Demo 不稳定 | presentation 翻车 | 准备 prerecorded demo + live demo 双保险 |

正式 report 里必须写 limitations 和 critical reflection，不要隐藏问题。

---

## 15. 隐私与伦理设计

本项目涉及 webcam 和 microphone，因此必须在系统和 report 中明确 privacy boundary。

建议原则：

1. **Local-first processing**  
   Webcam frame 尽量本地处理，不上传原始视频。

2. **Feature-only logging**  
   实验记录 gaze grid、AOI id、confidence、transcript、interaction logs，不存原始人脸视频。

3. **Explicit consent**  
   用户开始 session 前提示系统会使用 camera / microphone。

4. **No cognitive overclaim**  
   系统不声称知道用户真实 attention / confusion / understanding，只说 observable signals。

5. **User correction and control**  
   用户可确认、纠正、关闭 gaze input、改用 mouse click。

6. **No evaluation of ability or intelligence**  
   系统只提供学习支持，不评价用户聪明与否、学习能力强弱。

---

## 16. 项目 Claim 边界

### 可以说

- We estimate coarse gaze/head-pose cues.
- We map gaze cues to slide AOIs.
- We support deictic learning queries such as “explain this.”
- We provide uncertainty-aware target confirmation.
- We evaluate AOI grounding accuracy and interaction usability.

### 不要说

- We accurately track eye gaze using webcam.
- We know what the learner is thinking.
- We detect confusion reliably.
- We significantly improve learning outcomes.
- We outperform NotebookLM / Gemini / Copilot overall.
- We build a general AI tutor for all materials.

---

## 17. 当前推荐最终描述

可以作为 proposal / abstract 初稿：

> AttentiveSlides is a low-cost gaze-and-voice grounded AI tutor for slide-based learning. Existing AI learning assistants can answer questions about uploaded slides, but they usually require learners to explicitly describe or select the target content. AttentiveSlides explores a more human-centered interaction design: the learner looks at a slide region and asks a deictic question such as “explain this,” while the system uses webcam-based coarse gaze/head-pose estimation to infer the intended AOI. To address the unreliability of low-cost gaze estimation, the system explicitly displays the predicted target, confidence, and evidence, and allows user correction before generating a slide-grounded explanation. The project contributes a low-cost gaze-grounded reference resolution pipeline, an uncertainty-aware tutoring loop, and slide-grounded learning actions such as explanation, comparison, summarization, and quiz generation.

---

## 18. 总体判断

**AttentiveSlides 比 HAI-Pomodoro 更适合作为主项目。**

原因：

1. 它的 HAI 核心更明确：human attention as interaction context。
2. 它不是简单检测状态，而是设计新的 human-AI interaction primitive。
3. 它有清楚的技术闭环：webcam gaze → AOI → voice intent → grounded tutor response。
4. 它可以做明确实验：AOI grounding accuracy + interaction efficiency / usability。
5. 它的风险可控：只做 coarse AOI，不做精确 gaze tracking。
6. 它的 limitation 可以被转化为设计点：uncertainty display + user correction。

番茄钟方向可以后续作为 **study session summary / reflective learning trace** 的扩展，但不建议抢主线。

---

## 19. 下一步任务清单

1. 明确最终题目和 3 条 contribution。
2. 做 related work table，覆盖 products + papers。
3. 选 1–2 套课程 slides 作为 demo materials。
4. 设计 AOI schema 和 manual annotation format。
5. 实现 PDF rendering + slide viewer。
6. 实现 MediaPipe gaze/head-pose prototype。
7. 实现 9-point calibration。
8. 接入 Whisper 或 text fallback。
9. 接入 LLM tutor prompt。
10. 完成 end-to-end demo。
11. 设计 AOI grounding experiment。
12. 设计 usability experiment。
13. 写 report skeleton。
14. 准备 presentation demo script。

