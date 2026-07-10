# Audio Usability Smoke Phrases

Use these short phrases for the next real recorded audio check. Record them in a
quiet room as separate wav files, or use the Streamlit audio input one by one.

Suggested filenames are local-only and should stay under
`data/audio_samples/recorded/`.

| Filename | Phrase |
|---|---|
| `smoke_01_explain_this.wav` | 解释这个 |
| `smoke_02_right_figure.wav` | 讲讲右边这个图 |
| `smoke_03_figure_meaning.wav` | 这个图是什么意思 |
| `smoke_04_summarize_slide.wav` | 总结这一页 |
| `smoke_05_quiz_concept.wav` | 考我一下这个概念 |
| `smoke_06_formula_steps.wav` | 一步一步解释这个公式 |
| `smoke_07_compare_previous.wav` | 这个和上一个有什么区别 |
| `smoke_08_review_where.wav` | 我该复习哪里 |
| `smoke_09_simplify.wav` | 讲简单一点 |
| `smoke_10_explain_english.wav` | explain this part |
| `smoke_11_function_english.wav` | explain this function |
| `smoke_12_chart_english.wav` | what does this chart mean |

Smoke checklist:

1. Transcription is understandable enough after optional manual correction.
2. Intent parsing returns the expected intent.
3. Deictic references such as `这个` or `this` trigger AOI confirmation.
4. The user can confirm or correct AOI before final tutor response.
5. The tutor response appears and remains grounded to slide/AOI context.

Do not use this small set for statistical ASR claims or fine-tuning. It is a
manual usability smoke set for the demo loop.
