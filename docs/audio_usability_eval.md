# Project-specific audio usability evaluation

This workflow evaluates reviewed command recordings through the existing adapter-backed
tutor pipeline. It is for user-recorded usability smoke tests, not model training.

## Private data boundary

Keep local recordings in the repository-root `audio_eval/` directory. That directory,
the generated `data/audio_eval/user_smoke_manifest.csv`, remote copies, and result JSON
files are ignored by Git. Do not add any of them to a commit.

The reviewed CSV uses exactly these fields:

```csv
case_id,audio_path,expected_text,scenario
```

`expected_text` is the speaker-approved reference for CER, deictic detection, explicit
target hints, confirmation mode, and response mode. For **intent** accuracy, known
`scenario` values map to a canonical intent phrase (for example, `explain_deictic` maps
to `explain this`). This makes an intent-parser failure visible even when the spoken phrase
is not yet covered by the rules. `unknown` keeps the reviewed text as its intent reference;
the evaluator never substitutes filename-derived text for the reviewed value.

## Local preparation

Generate the initial CSV once, then review its `expected_text` and `scenario` values:

```bash
python scripts/create_audio_smoke_manifest.py \
  --audio-dir audio_eval \
  --output data/audio_eval/user_smoke_manifest.csv
```

All current recordings are English. Use the default language (`en`) unless that changes.

## Evaluation commands

On the machine holding the recordings:

```bash
python evaluation/eval_audio_usability.py \
  --manifest data/audio_eval/user_smoke_manifest.csv \
  --audio-root audio_eval \
  --engine faster_whisper \
  --profile fast \
  --output data/audio_eval/results/user_smoke_fast.json

python evaluation/eval_audio_usability.py \
  --manifest data/audio_eval/user_smoke_manifest.csv \
  --audio-root audio_eval \
  --engine faster_whisper \
  --profile balanced \
  --output data/audio_eval/results/user_smoke_balanced.json
```

After copying recordings to a remote `data/audio_eval/user_smoke/` directory, preserve the
same CSV and change only `--audio-root`:

```bash
python evaluation/eval_audio_usability.py \
  --manifest data/audio_eval/user_smoke_manifest.csv \
  --audio-root data/audio_eval/user_smoke \
  --engine faster_whisper \
  --profile balanced \
  --output data/audio_eval/results/user_smoke_balanced.json
```

`--audio-root` maps the original CSV filename to the transferred audio directory without
encoding a Mac path in the repository. Run `accurate` only after `fast` and `balanced`
complete successfully.

Compare completed profiles:

```bash
python evaluation/compare_stt_profiles.py \
  --inputs data/audio_eval/results/user_smoke_fast.json data/audio_eval/results/user_smoke_balanced.json \
  --output data/audio_eval/results/profile_comparison.md
```

The comparison prioritizes intent, deictic detection, explicit target hints, confirmation
mode, and response mode before CER. It recommends `fast` only when every key semantic
metric is within 0.05 of `balanced` and end-to-end latency is at least 15% lower.
Otherwise it recommends `balanced` for interactive use. `accurate` can be recommended for
a recorded demo when it improves a key semantic metric by at least 0.05 and is no more than
twice the balanced end-to-end latency. CPU is fallback-only.

## Metric meanings

- `transcript_usable_rate`: non-empty STT results.
- `mean_cer`: character error rate against the reviewed English text.
- semantic accuracy fields: agreement between expected-text and STT-text pipeline states.
- `mean_transcription_latency_ms`: STT invocation only.
- `mean_end_to_end_latency_ms`: STT plus pipeline processing.

The default test suite uses the mock transcriber and requires no CUDA, model download,
real recording, or microphone.
