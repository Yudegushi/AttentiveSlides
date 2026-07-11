# AttentiveSlides Audio Next Goal：10 条本地语音 → 4060 部署评估 → Demo Audio Flow

> 面向 Codex Goal Mode 的任务说明。
> 本文按 `context / request / output / constraint / checkpoint` 写成可执行工程目标。
> 语音文件当前在 Mac 本机项目工作目录下的 `audio_eval/` 文件夹，全部为 `.m4a`。

---

## 0. 为什么这样写 Goal

Codex Goal Mode 不适合塞一整篇泛泛规划。更稳的写法是：

```text
Context：当前项目状态、已有接口、环境事实
Request：这次到底要完成什么
Output：交付哪些文件、脚本、结果
Constraint：明确不要做什么，避免 Codex 发散
Checkpoint：什么时候必须停下来问我
Definition of Done：做到什么算完成
```

本阶段目标不是继续增加系统框架，而是把已录好的 10 条 project-specific audio 真正接入现有 pipeline，并确定 demo 时的 STT profile。

---

## 1. Context

项目：`Yudegushi/AttentiveSlides`

当前分支状态：

- `main` 已有 Member 3/4 mock-driven system pipeline、Streamlit demo、adapter boundary。
- `codex-audio-first-step` 分支已完成 file-based STT integration、audio profile、recording helper、Streamlit audio upload / recorded path mode。
- 当前仍缺少：real user-recorded project-specific audio evaluation。
- 用户已经在 Mac 本机项目工作目录下录好 10 条 `.m4a` 语音，文件夹为：

```text
audio_eval/
```

文件名就是语音内容或语音内容的简写，例如：

```text
explain-this.m4a
```

已知远端 Linux + 4060 环境：

```text
SSH host: LenovoLinux_Dorm
Conda env: pyboe
Recommended env activation:
source /home/charles/miniconda3/etc/profile.d/conda.sh
conda activate pyboe
```

4060 上已有 faster-whisper 运行记录。当前 STT profile 设计：

| Profile | Model | Device | Compute | 用途 |
|---|---|---|---|---|
| fast | small | cuda | int8_float16 | 低延迟候选 |
| balanced | medium | cuda | int8_float16 | 默认 interactive demo 候选 |
| accurate | large-v3 | cuda | int8_float16 | 准确率候选 |
| cpu | small | cpu | int8 | 无 GPU fallback |

---

## 2. Request

请完成下一阶段 audio 工作：

```text
Mac 本机 audio_eval/*.m4a
→ 生成轻量 metadata manifest
→ 传输到 4060 Linux
→ 在 4060 上拉取/同步完整项目代码
→ 对 10 条真实语音做 STT profile evaluation
→ 根据结果建议 demo 默认 STT profile
→ 整理 Streamlit demo 的 audio flow
→ 验证 record-to-transcribe 的实时工作路径
→ merge main 前做自检，但不要自动合并 main
```

这次任务应能支持用户参与实时 eval：用户会在 4060 上实际说话 / 录音 / 查看 transcript 是否可用。

---

## 3. Scope

### 3.1 必做

1. 在 repo 中新增或完善 project-specific audio eval workflow。
2. 处理本地 `audio_eval/*.m4a`：
   - 不要 commit 私人音频。
   - 可以生成本地 manifest。
   - 可以传输到远端 gitignored 目录。
3. 支持 `.m4a`：
   - 优先直接让 faster-whisper / PyAV 读取 `.m4a`。
   - 如果失败，再转换成 `.wav`。
   - 转换时不要覆盖原文件。
4. 自动从文件名生成一个初始 CSV manifest。
5. 让用户只需要检查/修改简单字段，而不是手写复杂 JSON。
6. 在 4060 上对至少 `fast` 和 `balanced` 两个 profile 跑 eval；如时间允许，再跑 `accurate`。
7. 输出 profile 对比结果：
   - transcript usable rate
   - CER / rough text error
   - intent accuracy after STT
   - deictic detection accuracy after STT
   - explicit target hint accuracy
   - confirmation mode accuracy
   - response mode accuracy
   - mean transcription latency
   - mean end-to-end latency
8. 整理 Streamlit demo audio flow：
   - 上传/选择音频
   - Transcribe
   - Show transcript
   - 用户可编辑 transcript
   - Confirm AOI
   - Tutor response
9. 验证 record-to-transcribe 路径：
   - 不是 streaming ASR。
   - 是用户触发录音，保存短音频，再转写。
10. 合并到 `main` 前执行自检，并输出一份 merge-readiness summary。

---

## 4. Non-scope / Constraints

不要做：

```text
1. 不要实现 streaming ASR。
2. 不要实现 wake word / background listening。
3. 不要实现 speaker diarization。
4. 不要加入 FunASR。
5. 不要做模型微调。
6. 不要改变现有 Transcript / ResolvedQuery / InteractionResult schema，除非绝对必要。
7. 不要绕开现有 adapter-backed pipeline。
8. 不要 commit 私人音频、生成日志、模型权重、HF cache、large eval outputs。
9. 不要自动 merge 到 main。
10. 不要把用户的 Mac 本地绝对路径硬编码进 repo。
```

实时录音接口只允许做：

```text
push-to-record / record-to-file / transcribe-on-click
```

不允许做：

```text
continuous streaming / background microphone / always-on listening
```

---

## 5. Metadata / Manifest 设计

不要要求用户手写复杂 JSON。

### 5.1 初始 manifest 使用 CSV

路径建议：

```text
data/audio_eval/user_smoke_manifest.csv
```

CSV 字段：

```csv
case_id,audio_path,expected_text,scenario
```

示例：

```csv
explain_this,audio_eval/explain-this.m4a,explain this,explain_deictic
right_figure,audio_eval/explain-right-figure.m4a,explain right figure,explain_explicit_right
summarize_slide,audio_eval/summarize-this-slide.m4a,summarize this slide,summarize_whole_slide
```

### 5.2 文件名自动推断

请实现一个脚本从 `audio_eval/*.m4a` 自动生成初始 CSV：

```bash
python scripts/create_audio_smoke_manifest.py --audio-dir audio_eval --output data/audio_eval/user_smoke_manifest.csv
```

推断规则：

```text
case_id = 文件名去扩展名，把 "-" 替换成 "_"
expected_text = 文件名去扩展名，把 "-" 替换成 " "
scenario = 根据文件名关键词猜测
```

scenario 猜测规则可以简单：

| 文件名包含 | scenario |
|---|---|
| explain + this | explain_deictic |
| right + figure / right | explain_explicit_right |
| summarize | summarize_whole_slide |
| quiz / test | quiz_deictic |
| compare / difference | compare_deictic |
| simple / simplify | simplify_current |
| step | step_by_step_current |
| review | review_whole_slide |
| tired / break | break_or_short_recap |
| 其他 | unknown |

### 5.3 必须暂停让用户检查 manifest

生成 manifest 后必须暂停，提示用户检查：

```text
Please review data/audio_eval/user_smoke_manifest.csv:
- expected_text 是否等于实际说的话
- scenario 是否合理
Then rerun the eval command.
```

如果用户的语音是中文，但文件名是英文简写，那么 `expected_text` 需要用户手动改成中文，否则 CER 没意义。

---

## 6. Mac → 4060 传输

### 6.1 不要假设 Codex 一定能直接访问两台机器

如果 Codex 正在 Mac 上运行：

- 可以生成/执行 `rsync` 命令，把 `audio_eval/` 传到远端。
- 可以把 manifest 一起传过去。

如果 Codex 正在 4060 上运行：

- 它不能访问 Mac 的 `audio_eval/`，必须停下来要求用户从 Mac 上传/rsync。

### 6.2 推荐远端目录

不要放在 tracked 路径里。建议：

```text
<remote_repo>/data/audio_eval/user_smoke/
```

或：

```text
<remote_repo>/data/audio_samples/user_smoke/
```

要求这些目录必须 gitignored。

### 6.3 传输命令模板

如果远端 repo 路径能确定，例如：

```text
REMOTE_REPO=/home/charles/AttentiveSlides
```

则使用：

```bash
rsync -av --progress audio_eval/ LenovoLinux_Dorm:${REMOTE_REPO}/data/audio_eval/user_smoke/
rsync -av --progress data/audio_eval/user_smoke_manifest.csv LenovoLinux_Dorm:${REMOTE_REPO}/data/audio_eval/
```

如果远端 repo 路径不确定，必须先暂停询问用户。

---

## 7. 4060 上的代码同步与环境检查

在 4060 上执行：

```bash
ssh LenovoLinux_Dorm
cd <remote_repo>
git status
git fetch --all
git checkout codex-audio-first-step
git pull
source /home/charles/miniconda3/etc/profile.d/conda.sh
conda activate pyboe
python --version
nvidia-smi
```

然后跑基础检查：

```bash
python -m unittest discover -s tests -v
python scripts/transcribe_audio_file.py --audio data/audio_samples/explain_this.wav --engine mock --profile balanced
python scripts/demo_audio_to_tutor_loop.py --audio data/audio_samples/right_figure.wav --engine mock --profile fast --sensing-preset high_confidence_right_figure
```

如果基础检查失败，先修基础问题，不要继续 real audio eval。

---

## 8. Project-specific Audio Eval

### 8.1 Eval 命令

建议新增或扩展：

```bash
python evaluation/eval_audio_usability.py \
  --manifest data/audio_eval/user_smoke_manifest.csv \
  --engine faster_whisper \
  --profile fast \
  --output data/audio_eval/results/user_smoke_fast.json
```

再跑：

```bash
python evaluation/eval_audio_usability.py \
  --manifest data/audio_eval/user_smoke_manifest.csv \
  --engine faster_whisper \
  --profile balanced \
  --output data/audio_eval/results/user_smoke_balanced.json
```

如果时间允许：

```bash
python evaluation/eval_audio_usability.py \
  --manifest data/audio_eval/user_smoke_manifest.csv \
  --engine faster_whisper \
  --profile accurate \
  --output data/audio_eval/results/user_smoke_accurate.json
```

### 8.2 输出 summary

新增：

```bash
python evaluation/compare_stt_profiles.py \
  --inputs data/audio_eval/results/user_smoke_fast.json data/audio_eval/results/user_smoke_balanced.json data/audio_eval/results/user_smoke_accurate.json \
  --output data/audio_eval/results/profile_comparison.md
```

如果没有跑 `accurate`，脚本也应该能处理两个输入。

### 8.3 默认 profile 选择规则

请在 summary 中自动给一个建议：

```text
如果 fast 的 intent/deictic/response_mode 指标与 balanced 接近，且 latency 明显更低：
    recommend fast

如果 fast 在关键 intent 或 deictic 上出错，而 balanced 正确：
    recommend balanced

如果 balanced 仍然在关键短句上出错，accurate 明显更好且 latency 可接受：
    recommend accurate for recorded demo, balanced for live interactive demo

cpu 只作为 fallback，不作为主 demo profile
```

最终推荐不要只看 CER，要优先看：

```text
intent accuracy
deictic detection
explicit target hint
confirmation mode
response mode
latency
```

---

## 9. Streamlit Demo Audio Flow

目标是 presentation 时路径最短：

```text
上传/选择音频
→ Transcribe
→ Show transcript
→ 用户可编辑 transcript
→ Confirm AOI
→ Tutor response
```

请检查并改进 `apps/streamlit_demo.py`：

1. Audio mode 应该默认使用 `balanced`，但允许选择 `fast / balanced / accurate / cpu`。
2. 音频输入应支持：
   - uploaded `.m4a / .wav / .mp3`
   - local recorded wav path
   - 如果当前 Streamlit 版本支持 `st.audio_input`，允许直接录音。
3. Transcribe 按钮必须是手动触发。
4. 转写结果写入 learner utterance text box。
5. 用户可以修改 transcript。
6. 后续仍走已有 AOI confirmation/correction flow。
7. pending confirmation 时不要展示 final AOI-specific answer。
8. confirmed/corrected 后再展示 final tutor response。
9. UI 应显示 STT profile、latency、transcript source。
10. 不要加入后台录音。

---

## 10. Record-to-Transcribe 实时工作验证

已有或新增命令：

```bash
python scripts/record_audio_file.py --duration 4 --output data/audio_samples/recorded/live_smoke.wav
python scripts/transcribe_audio_file.py --audio data/audio_samples/recorded/live_smoke.wav --engine faster_whisper --profile balanced
python scripts/demo_audio_to_tutor_loop.py --audio data/audio_samples/recorded/live_smoke.wav --engine faster_whisper --profile balanced --sensing-preset high_confidence_right_figure
```

目标是验证：

```text
用户实际说一句话
→ 系统录成短音频
→ STT 转成 transcript
→ pipeline 产生正确 intent/reference/tutor state
```

如果 microphone / sounddevice 在远端不可用，必须停下来说明原因，不要改成 streaming workaround。

---

## 11. Merge 前自检

不要自动 merge main。只做 merge-readiness check。

必须执行：

```bash
python -m unittest discover -s tests -v
python scripts/demo_tutor_loop.py
python scripts/demo_audio_to_tutor_loop.py --audio data/audio_samples/right_figure.wav --engine mock --profile fast --sensing-preset high_confidence_right_figure
python evaluation/eval_reference_resolution.py
python evaluation/eval_scenario_outputs.py
```

如果 real audio files available，再执行：

```bash
python evaluation/eval_audio_usability.py --manifest data/audio_eval/user_smoke_manifest.csv --engine faster_whisper --profile balanced
```

检查 git hygiene：

```bash
git status --short
git check-ignore -v data/audio_eval/user_smoke/* || true
git check-ignore -v data/audio_samples/recorded/* || true
```

确保没有 commit：

```text
private audio
generated logs
model cache
large eval outputs
local environment files
```

最后输出：

```text
MERGE_READINESS.md 或 docs/audio_merge_readiness.md
```

内容包括：

```text
1. 当前分支
2. 最新 commit
3. 执行过的命令
4. 测试结果
5. real audio eval 结果
6. 推荐 demo STT profile
7. 已知限制
8. main merge 前还需要用户确认的事项
```

---

## 12. Checkpoints：什么时候必须停下来问我

Codex 必须在以下情况暂停：

1. 找不到 Mac 本地 `audio_eval/` 文件夹。
2. `audio_eval/` 里不是 10 个 `.m4a`，或者有无法识别的文件。
3. 远端 SSH host `LenovoLinux_Dorm` 不可达。
4. 不知道远端 repo 路径。
5. 生成 manifest 后，需要我检查 `expected_text` 和 `scenario`。
6. 发现语音内容不是文件名推断出的语言，例如文件名英文但实际语音中文。
7. 4060 上 conda env `pyboe` 不存在或无法激活。
8. `faster-whisper` / CUDA 运行失败。
9. m4a 不能被直接读取，且 ffmpeg 不可用。
10. real audio eval 结果明显异常，例如 transcript 全空、intent 全错。
11. Streamlit audio flow 需要浏览器权限或人工点击验证。
12. record-to-transcribe 需要我现场说话。
13. merge 前出现未跟踪的私人音频或大文件。
14. 需要执行真正的 `git merge` 或推送到 main。

---

## 13. Deliverables

本次工作完成后，应交付：

```text
1. scripts/create_audio_smoke_manifest.py
2. evaluation/eval_audio_usability.py
3. evaluation/compare_stt_profiles.py
4. docs/audio_usability_eval.md
5. docs/audio_merge_readiness.md 或 MERGE_READINESS.md
6. 更新 docs/audio_deployment.md（如需要）
7. 更新 apps/streamlit_demo.py 的 audio flow（如需要）
8. 必要 tests，且 default tests 不依赖 real audio / CUDA / microphone
9. 本地/远端 gitignored audio_eval README 或 .gitkeep
```

不要求交付私人音频文件。

---

## 14. Definition of Done

完成标准：

```text
1. 10 条 m4a 音频可以生成简单 CSV manifest。
2. manifest 经用户确认后，可以在 4060 上跑 real STT eval。
3. 至少 fast 和 balanced 两个 STT profile 有对比结果。
4. 系统能给出 demo 默认 profile 建议。
5. Streamlit demo 的 audio path 清晰：audio -> transcript -> editable text -> AOI confirmation -> tutor response。
6. record-to-transcribe 路径可在 4060 上人工验证，或明确记录硬件/权限原因。
7. 所有默认 unit tests 通过。
8. 不提交私人音频和大文件。
9. 合并 main 前有自检 summary。
```

---

## 15. Paste-ready Codex Goal Prompt

下面这段可以直接粘给 Codex Goal Mode：

```text
Context:
You are working on Yudegushi/AttentiveSlides. Member 3/4 system pipeline, adapter boundary, Streamlit demo, and file-based faster-whisper STT integration already exist on the audio branch. The next missing step is project-specific user-recorded audio evaluation and demo audio-flow hardening. The user has recorded 10 local .m4a files in the Mac-side project working directory: audio_eval/. Filenames describe the spoken content, e.g. explain-this.m4a. The Linux 4060 machine is reachable as SSH host LenovoLinux_Dorm, and the audio environment is the conda env pyboe.

Request:
Implement and verify the next audio workflow:
1. Generate a simple CSV manifest from audio_eval/*.m4a.
2. Pause for user review of expected_text and scenario.
3. Transfer the audio and manifest to the 4060 repo under gitignored data/audio_eval/user_smoke/.
4. Pull/sync the full project on the 4060.
5. Run real STT evaluation on the 10 project-specific audio samples.
6. Compare STT profiles fast, balanced, and accurate when feasible.
7. Recommend the demo default STT profile based on intent/deictic/response_mode accuracy and latency.
8. Harden the Streamlit audio flow so presentation path is short:
   upload/select audio -> Transcribe -> Show/edit transcript -> Confirm AOI -> Tutor response.
9. Verify record-to-transcribe workflow, but do not implement streaming ASR.
10. Run merge-readiness self-check before main merge, but do not merge to main.

Output:
Deliver scripts/docs/tests as needed:
- scripts/create_audio_smoke_manifest.py
- evaluation/eval_audio_usability.py
- evaluation/compare_stt_profiles.py
- docs/audio_usability_eval.md
- docs/audio_merge_readiness.md or MERGE_READINESS.md
- Streamlit audio flow refinements if needed
- tests using mock transcriber only for default test suite

Constraints:
- Do not commit private audio, generated logs, model weights, cache files, or large eval outputs.
- Do not implement streaming ASR, wake word, background listening, diarization, FunASR, or model fine-tuning.
- Do not change existing Transcript / ResolvedQuery / InteractionResult schemas unless absolutely necessary.
- Do not bypass the existing adapter-backed pipeline.
- Default tests must not require CUDA, microphone, real audio, faster-whisper, or downloaded models.
- Do not automatically merge or push to main.

Checkpoints:
Stop and ask the user if:
- audio_eval/ is missing or does not contain the expected 10 .m4a files.
- the remote repo path on LenovoLinux_Dorm is unknown.
- SSH / conda / CUDA / faster-whisper fails.
- the generated manifest needs expected_text/scenario confirmation.
- m4a cannot be decoded and ffmpeg is unavailable.
- Streamlit audio input requires browser/manual validation.
- record-to-transcribe requires the user to speak.
- any private audio or large generated file is about to be committed.
- a real merge into main is needed.

Definition of Done:
- 10 m4a files have a simple reviewed CSV manifest.
- Real STT eval runs on 4060 for at least fast and balanced profiles.
- A profile comparison summary recommends the demo default STT profile.
- Streamlit demo supports the short presentation audio path.
- Record-to-transcribe path is verified or clearly blocked with reason.
- Unit tests pass.
- Merge-readiness summary is produced.
- No private audio or large artifacts are committed.
```
