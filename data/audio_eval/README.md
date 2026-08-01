# Audio Evaluation Data

This directory is for local public-audio evaluation artifacts.

The next-stage downloader writes PolyAI/minds14 zh-CN samples to:

```text
data/audio_eval/minds14_zh_cn/
```

Generated wav files and manifests are ignored by Git. Keep only this README
tracked.

## Project-specific private recordings

Reviewed user recordings are kept locally in root `audio_eval/` and transferred to an
ignored `data/audio_eval/user_smoke/` directory only on an evaluation machine. The matching
CSV and profile results are also ignored and remain outside Git.

Install the canonical project environment before preparing or evaluating
audio:

```bash
python -m pip install -r requirements.txt
```

Recommended local preparation command:

```bash
python scripts/prepare_audio_eval_samples.py --limit 20
```

Recommended evaluation command:

```bash
python evaluation/eval_audio_pipeline.py \
  --manifest data/audio_eval/minds14_zh_cn/manifest.json \
  --engine faster_whisper \
  --model small \
  --device cuda \
  --compute-type int8_float16 \
  --language zh
```
